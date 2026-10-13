"""Exact encrypted source custody using the existing Windows secure keyring.

Source bodies are kept whole. Operational projections contain references, not
credential values. AES-CBC is authenticated with a separate HMAC-SHA256 key.
Every peer uses the same direct secure reference; no holder or admission list.
"""
from __future__ import annotations
import base64
import ctypes
import hashlib
import hmac
import json
import os
import sqlite3
import sys
from pathlib import Path
from threading import Lock, RLock
from ctypes import wintypes

KEY_TARGET = "commons:swarm-telemetry:source-custody-key"
KEY_REFERENCE = "telemetry/source-custody-key"
_CUSTODY_WRITE_LOCK = RLock()

class ClosingConnection(sqlite3.Connection):
    """Retain SQLite transaction semantics and close each completed context."""
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class _Credential(ctypes.Structure):
    _fields_=[("Flags",wintypes.DWORD),("Type",wintypes.DWORD),("TargetName",wintypes.LPWSTR),("Comment",wintypes.LPWSTR),("LastWritten",wintypes.FILETIME),("CredentialBlobSize",wintypes.DWORD),("CredentialBlob",ctypes.POINTER(ctypes.c_ubyte)),("Persist",wintypes.DWORD),("AttributeCount",wintypes.DWORD),("Attributes",ctypes.c_void_p),("TargetAlias",wintypes.LPWSTR),("UserName",wintypes.LPWSTR)]

def secure_key():
    if os.name!="nt":
        raise RuntimeError("Use the existing shared secure facility to retrieve the source custody key on this runtime.")
    advapi=ctypes.WinDLL("Advapi32.dll",use_last_error=True)
    ptr=ctypes.POINTER(_Credential)()
    advapi.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.POINTER(_Credential))]
    advapi.CredReadW.restype=wintypes.BOOL
    if advapi.CredReadW(KEY_TARGET,1,0,ctypes.byref(ptr)):
        try: data=ctypes.string_at(ptr.contents.CredentialBlob,ptr.contents.CredentialBlobSize)
        finally: advapi.CredFree(ptr)
        if len(data)!=64: raise RuntimeError("Source custody key has an incompatible length")
        return data
    error=ctypes.get_last_error()
    if error!=1168: raise OSError(error,"Secure source key could not be read")
    data=os.urandom(64)
    blob=(ctypes.c_ubyte*len(data)).from_buffer_copy(data)
    item=_Credential()
    item.Type=1
    item.TargetName=KEY_TARGET
    item.Comment="Shared exact telemetry source custody; directly retrievable by every Commons peer"
    item.CredentialBlobSize=len(data)
    item.CredentialBlob=ctypes.cast(blob,ctypes.POINTER(ctypes.c_ubyte))
    item.Persist=2
    item.UserName="Commons"
    advapi.CredWriteW.argtypes=[ctypes.POINTER(_Credential),wintypes.DWORD]
    advapi.CredWriteW.restype=wintypes.BOOL
    if not advapi.CredWriteW(ctypes.byref(item),0): raise OSError(ctypes.get_last_error(),"Shared source custody key could not be saved")
    return data

def _portable_aes(data,key,iv,decrypt=False):
    try:
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError:
        bundled = Path.home()/".cache"/"codex-runtimes"/"codex-primary-runtime"/"dependencies"/"python"/"Lib"/"site-packages"
        if bundled.is_dir() and str(bundled) not in sys.path:
            sys.path.insert(0, str(bundled))
        from cryptography.hazmat.primitives import padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    cipher=Cipher(algorithms.AES(key),modes.CBC(iv))
    if decrypt:
        decryptor=cipher.decryptor()
        padded=decryptor.update(data)+decryptor.finalize()
        unpadder=padding.PKCS7(128).unpadder()
        return unpadder.update(padded)+unpadder.finalize()
    padder=padding.PKCS7(128).padder()
    padded=padder.update(data)+padder.finalize()
    encryptor=cipher.encryptor()
    return encryptor.update(padded)+encryptor.finalize()


def _aes(data,key,iv,decrypt=False):
    if os.name!="nt":
        return _portable_aes(data,key,iv,decrypt)
    bcrypt=ctypes.WinDLL("bcrypt.dll")
    handle=ctypes.c_void_p()
    key_handle=ctypes.c_void_p()
    def checked(status):
        if status: raise OSError("Native source encryption failed: "+str(status))
    bcrypt.BCryptOpenAlgorithmProvider.argtypes=[ctypes.POINTER(ctypes.c_void_p),wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.ULONG]
    checked(bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(handle),"AES",None,0))
    try:
        mode=ctypes.create_unicode_buffer("ChainingModeCBC")
        bcrypt.BCryptSetProperty.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR,ctypes.c_void_p,wintypes.ULONG,wintypes.ULONG]
        checked(bcrypt.BCryptSetProperty(handle,"ChainingMode",mode,ctypes.sizeof(mode),0))
        size=wintypes.ULONG()
        read=wintypes.ULONG()
        bcrypt.BCryptGetProperty.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR,ctypes.c_void_p,wintypes.ULONG,ctypes.POINTER(wintypes.ULONG),wintypes.ULONG]
        checked(bcrypt.BCryptGetProperty(handle,"ObjectLength",ctypes.byref(size),ctypes.sizeof(size),ctypes.byref(read),0))
        obj=ctypes.create_string_buffer(size.value)
        material=ctypes.create_string_buffer(key)
        bcrypt.BCryptGenerateSymmetricKey.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p),ctypes.c_void_p,wintypes.ULONG,ctypes.c_void_p,wintypes.ULONG,wintypes.ULONG]
        checked(bcrypt.BCryptGenerateSymmetricKey(handle,ctypes.byref(key_handle),obj,size.value,material,len(key),0))
        incoming=ctypes.create_string_buffer(data)
        vector=ctypes.create_string_buffer(iv)
        output=ctypes.create_string_buffer(len(data)+32)
        actual=wintypes.ULONG()
        operation=bcrypt.BCryptDecrypt if decrypt else bcrypt.BCryptEncrypt
        operation.argtypes=[ctypes.c_void_p,ctypes.c_void_p,wintypes.ULONG,ctypes.c_void_p,ctypes.c_void_p,wintypes.ULONG,ctypes.c_void_p,wintypes.ULONG,ctypes.POINTER(wintypes.ULONG),wintypes.ULONG]
        checked(operation(key_handle,incoming,len(data),None,vector,len(iv),output,len(output),ctypes.byref(actual),1))
        return output.raw[:actual.value]
    finally:
        if key_handle: bcrypt.BCryptDestroyKey(key_handle)
        if handle: bcrypt.BCryptCloseAlgorithmProvider(handle,0)

class Custody:
    def __init__(self,path,key_loader=None,write_lock=None):
        self.path=str(path)
        self._key=None
        self._key_lock=Lock()
        self._key_loader=key_loader
        self._write_lock=write_lock or _CUSTODY_WRITE_LOCK
        with self._write_lock,sqlite3.connect(self.path,timeout=30,factory=ClosingConnection) as db:
            db.execute("PRAGMA busy_timeout=30000")
            db.execute("CREATE TABLE IF NOT EXISTS source_records (ref TEXT PRIMARY KEY,source_id TEXT,sha256 TEXT,byte_length INTEGER,character_length INTEGER,iv BLOB,ciphertext BLOB,mac BLOB,format TEXT,key_reference TEXT)")
    def key(self):
        if self._key is None:
            with self._key_lock:
                if self._key is None:
                    data=self._key_loader(KEY_REFERENCE) if self._key_loader else None
                    if isinstance(data,str):
                        try: data=base64.b64decode(data,validate=True)
                        except (ValueError,base64.binascii.Error): data=data.encode("utf-8")
                    candidate=data if data is not None else secure_key()
                    if not isinstance(candidate,bytes) or len(candidate)!=64:
                        raise RuntimeError("Shared source custody key has an incompatible length")
                    self._key=candidate
        return self._key

    def prepare(self,value,source_id):
        if isinstance(value,bytes): raw=value; fmt="bytes"
        elif isinstance(value,str): raw=value.encode("utf-8"); fmt="utf-8"
        else: raw=json.dumps(value,ensure_ascii=False,separators=(",",":"),default=str).encode("utf-8"); fmt="json-utf-8"
        digest=hashlib.sha256(raw).hexdigest()
        ref="source:"+digest
        try: chars=len(raw.decode("utf-8"))
        except UnicodeDecodeError: chars=None
        key=self.key()
        iv=os.urandom(16)
        encrypted=_aes(raw,key[:32],iv)
        mac=hmac.new(key[32:],b"swarm-source-v1"+iv+encrypted,hashlib.sha256).digest()
        record=(ref,str(source_id),digest,len(raw),chars,iv,encrypted,mac,fmt,KEY_REFERENCE)
        reference={"ref":ref,"sha256":digest,"bytes":len(raw),"characters":chars}
        return reference,record

    def insert_prepared(self,db,records):
        if records:
            db.executemany("INSERT OR IGNORE INTO source_records VALUES (?,?,?,?,?,?,?,?,?,?)",records)

    def seal(self,value,source_id):
        reference,record=self.prepare(value,source_id)
        with self._write_lock,sqlite3.connect(self.path,timeout=30,factory=ClosingConnection) as db:
            db.execute("PRAGMA busy_timeout=30000")
            self.insert_prepared(db,[record])
        return reference
    def _record(self,ref):
        with sqlite3.connect(self.path,timeout=30,factory=ClosingConnection) as db:
            db.execute("PRAGMA busy_timeout=30000")
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM source_records WHERE ref=?",(ref,)).fetchone()
        if not row: raise KeyError(ref)
        return dict(row)
    def envelope(self,ref):
        result=self._record(ref)
        for field in ("iv","ciphertext","mac"): result[field]=base64.b64encode(result[field]).decode("ascii")
        result.update(encryption="AES-256-CBC + HMAC-SHA256",source_exact=True,credential_access="Existing direct shared secure facility",key_reference=KEY_REFERENCE)
        return result
    def read(self,ref):
        record=self._record(ref)
        iv,cipher,mac=(record[field] for field in ("iv","ciphertext","mac"))
        key=self.key()
        expected=hmac.new(key[32:],b"swarm-source-v1"+iv+cipher,hashlib.sha256).digest()
        if not hmac.compare_digest(expected,mac): raise ValueError("Source authentication failed")
        raw=_aes(cipher,key[:32],iv,decrypt=True)
        if hashlib.sha256(raw).hexdigest()!=record["sha256"]: raise ValueError("Source content mismatch")
        return raw
