@echo off
cd /d "%~dp0"
echo ==> Creating virtual environment in venv
python -m venv venv || goto :err
call venv\Scripts\activate.bat
echo ==> Installing packages
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :err
if not exist .env (
  echo ==> Writing .env
  for /f %%i in ('python -c "import secrets;print(secrets.token_urlsafe(60))"') do set SECRET=%%i
  (echo DEBUG=1& echo SECRET_KEY=%SECRET%& echo ALLOWED_HOSTS=localhost,127.0.0.1) > .env
)
python manage.py makemigrations core || goto :err
python manage.py migrate || goto :err
python manage.py seed --type artist || goto :err
python manage.py collectstatic --noinput
echo.
echo ==> Create the OWNER account
python manage.py createsuperuser
echo.
echo Done. Start the site with run.bat then open http://127.0.0.1:8000
goto :eof
:err
echo Setup failed. Read the message above.
exit /b 1
