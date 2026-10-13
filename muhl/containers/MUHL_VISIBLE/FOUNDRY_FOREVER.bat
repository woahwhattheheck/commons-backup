@echo off
REM Compatibility tombstone. The former version ran Python forever, restarted
REM every five seconds, and could be registered at logon. Foundry work now runs
REM on an explicit GitHub-hosted Actions runner and returns a binary artifact.
echo REFUSE_LOCAL_COMPUTE: dispatch .github/workflows/muhlnickel-foundry-cloud.yml
exit /b 2
