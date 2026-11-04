#!/usr/bin/env bash
# One-time setup: creates the virtual environment, installs everything, builds the database,
# adds starter content and asks you to create the owner account.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

echo "==> Creating virtual environment in ./venv"
"$PY" -m venv venv
. venv/bin/activate

echo "==> Installing packages"
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  echo "==> Writing .env"
  SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(60))")
  cat > .env <<ENV
DEBUG=1
SECRET_KEY=$SECRET
ALLOWED_HOSTS=localhost,127.0.0.1
ENV
fi

echo "==> Building the database"
python manage.py makemigrations core
python manage.py migrate
python manage.py seed --type artist
python manage.py collectstatic --noinput

echo
echo "==> Create the OWNER account (this is the only login that can edit the site)"
python manage.py createsuperuser

echo
echo "Done. Start the site with:  ./run.sh   then open http://127.0.0.1:8000"
