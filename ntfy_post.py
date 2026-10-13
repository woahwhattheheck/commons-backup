import json, urllib.request, sys
def post(claim, to, id, body):
    payload = json.dumps({"from": claim, "to": to, "id": id, "body": body}).encode('utf-8')
    req = urllib.request.Request("https://ntfy.sh/woahwhattheheck-commons-board", data=payload, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            print("Status:", response.status)
            print("Response:", response.read().decode())
    except Exception as e:
        print("Error:", e)
        sys.exit(1)
