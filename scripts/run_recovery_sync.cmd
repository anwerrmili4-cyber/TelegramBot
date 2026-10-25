@echo off
cd /d "%~dp0.."
py -3 "%~dp0sync_recovery_db.py"
