# One site, any type (Django)

One website that becomes a **musician page, portfolio, company page or online store** by logging in, editing and toggling. Built with Django, so edits are saved in a real database and appear for every visitor.

## Run it

```bash
./setup.sh      # Windows: setup.bat   (creates ./venv, installs everything, builds the DB, asks for the owner login)
./run.sh        # Windows: run.bat     → http://127.0.0.1:8000
```

Run the checks any time: `venv/bin/python manage.py test`

## Using it

1. The owner login is hidden from visitors. Click the site name in the header three consecutive times to open the login page; the first two clicks stay on the page. Both staff owner accounts and the platform superuser can sign in. For a regular owner account, enable **Staff status** and leave **Superuser status** unchecked; the superuser has full site-design and account-management access. This is only a way to keep the login link out of sight; authentication and role checks still protect access.
2. The platform superuser has full site-design access. Add Spotify releases from Dashboard → Catalog by pasting a track URL or Spotify iframe embed code; the site uses Spotify's public oEmbed endpoint to fill the track title and cover art, with no API credentials. The release page embeds the Spotify player. Artist catalogs are not imported, and track descriptions can be entered manually. Previously saved Spotify releases and hero-track data are retained. In Edit mode, reorder catalog releases in the home-page rail by dragging them or using the ↑/↓ controls; the order saves automatically and is used on the catalog page too. Regular staff owners cannot change platform-wide settings. Press **Edit mode** (bottom bar) to change copy, images, visibility, sections, theme, or site type. When finished, press **Editing · tap to save**; pending text changes are saved before edit mode closes. Stay on the live page:
   - click any text to type; it saves when you click away. Links remain clickable; Alt-click a link label to edit its text.
   - hover an element to reveal its **eye** control; on touch devices, tap the element first. The eye shows or hides it for visitors. This includes header icons, navigation links, social icons, and the scrolling strip.
   - edit the scrolling strip between the hero and the next section in place, or toggle it with its eye control
   - **Change image** on pictures, **↑ ↓ 👁** on each section
   - **Site** panel: switch site type (artist, portfolio, company, store), theme, and turn **Releases/Shop, Blog, News** sections on or off
3. **Dashboard** (`/dashboard/`) lets regular staff owners create, edit, publish, and delete **Releases & Shop (catalog), Blog and News**, manage Orders and Messages, and update their contact details and social profiles. Their Profile settings also include a **Display location map** toggle. They cannot change the site type, theme, layout, sections, or site-wide copy/images. The platform superuser can access those settings. Add profile links for Instagram, TikTok, LinkedIn, Facebook, X, YouTube, Spotify, Threads, Twitch, SoundCloud, Apple Music, Bandcamp, Pinterest, Snapchat, Telegram, Discord, GitHub, Behance, Dribbble, Medium, Vimeo, Reddit, Mastodon, Bluesky and your website in the collapsed **Social profile links** group. The footer displays up to three configured profile links. WhatsApp uses the owner number field.
   To provision or update a business owner, sign in as the platform superuser and use **Manage logins** in the dashboard (or `/django-admin/`). Add a user and enable **Staff status** but leave **Superuser status** unchecked. Only the platform superuser can manage accounts or site-wide design/settings.
4. **Product checkout and Paystack:** priced catalog items have a product page and checkout. Add a Paystack **test secret key** to `PAYSTACK_SECRET_KEY` in `.env`, leave `PAYSTACK_MODE=test`, and use Naira (`₦`) as the store currency. Checkout redirects to Paystack hosted checkout with card and bank-transfer channels requested; card details are entered on Paystack and are never collected or stored by this app. Bank transfer/temporary account options depend on the channels enabled for your Paystack merchant account and the transaction. If bank transfer is not available on the hosted payment page, contact Paystack to enable/confirm the channel for your account. The return page verifies transactions with Paystack before an order is marked paid. Configure the public webhook URL as `https://yourdomain.com/payment/paystack/webhook/` in the Paystack dashboard for reliable background confirmation. Keep `PAYSTACK_SECRET_KEY` private; it is never sent to the browser. Without a valid key, checkout explicitly saves an **unpaid order request** only; no payment is taken and no ticket is issued.
5. **Paystack settlements:** add and verify the business bank account in your Paystack dashboard and confirm the settlement schedule/requirements with Paystack. Paystack settles eligible payments to that account according to its settlement schedule; this is not an immediate withdrawal feature in this Django site. Settlement timing, fees, and eligibility are controlled by Paystack and your merchant account.
6. **Switching Paystack live:** first complete test transactions with test keys, including a card payment and a bank-transfer payment if Paystack enables that method in test mode. When ready, replace the secret with the Paystack **live secret key** and set `PAYSTACK_MODE=live`, then restart the app. The mode and secret-key prefix must match (`sk_test_` or `sk_live_`), preventing accidental live payments while in test mode. Add the live webhook URL in Paystack, confirm live payment channels and the settlement bank account with Paystack, and run a low-value live transaction to validate production configuration.
7. **Event tickets:** mark a priced catalog item as **Sell event tickets**. Verified Paystack payments automatically mark the order paid and generate one unique ticket per quantity. The buyer's private order-status URL shows valid tickets, each with attendee details, a QR code, a downloadable QR image, and a printable page. An order submission is not a payment: pending orders show an explicit unpaid status and have no valid tickets. Manual dashboard payment confirmation remains available for offline orders. Tickets are not issued or considered valid before payment confirmation.
8. **Contact:** the Contact page includes the About story and details, icons for configured social profiles, contact form, and an embedded Google Map for the address saved in Dashboard → Profile/Settings when **Display location map** is enabled. The old `/about/` address redirects to Contact.
9. **Email notifications:** set the recipient in Dashboard → Settings → *Order and contact notification email*. Configure `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` in `.env` to send alerts through SMTP. Never put app passwords in source control or dashboard fields. Orders and messages remain saved in the dashboard if SMTP is not configured or delivery fails; checkout and contact forms report the delivery problem.

### Content types and detail pages
- **Catalog** items with a price above 0 are products: a **product page** (gallery, price, description, *Order now*). With price 0 they are releases/services: same layout with *Listen now* (set a link) or *Enquire*.
- **Blog** and **News** items open an **article page** (title, image, date, text, keep-reading).
- The section names (Releases, Shop, Services…) change with the site type or in Settings.

## Security built in
Hashed passwords and sessions, CSRF on every form and edit call, server-side role checks for dashboard and design operations, login limited to 5 tries per 15 minutes, only active staff/superuser accounts can log in, uploads are validated, stripped of metadata and re-encoded to WebP, article text is escaped, honeypot on the contact form, secure cookies and HSTS in production.

## Going live
1. Set `.env` from `.env.example` (`DEBUG=0`, a long `SECRET_KEY`, your domain).
2. `venv/bin/python manage.py migrate && venv/bin/python manage.py collectstatic --noinput`
3. Run `venv/bin/gunicorn config.wsgi --bind 127.0.0.1:8000` behind Caddy or nginx for HTTPS. Let the web server serve `/media/` directly for speed.
4. Back up `db.sqlite3` (or your Postgres) and the `media/` folder daily.
5. For PostgreSQL set the `POSTGRES_*` values in `.env`.
6. Apply new schema changes with `venv/bin/python manage.py migrate` (Windows: `venv\Scripts\python.exe manage.py migrate`).

### Deploying on Vercel

Vercel detects this Django project from `manage.py`; `.python-version` selects Python 3.12. Connect the GitHub repository to Vercel and add these Production environment variables in the Vercel project settings:

- `SECRET_KEY`: a newly generated, private Django secret key.
- `DEBUG`: `0`.
- `DATABASE_URL`: the Neon PostgreSQL connection string, including its required SSL parameters.
- `CLOUDINARY_URL`: the private Cloudinary URL from its dashboard, for persistent uploaded images.
- `CSRF_TRUSTED_ORIGINS`: the full HTTPS origin, such as `https://your-project.vercel.app` (add custom domains too).
- `ALLOWED_HOSTS`: comma-separated Vercel and custom hostnames if using custom domains. `.vercel.app` subdomains are allowed by default.
- `PAYSTACK_SECRET_KEY`: only if enabling online payments.

The database and uploaded media are not included in GitHub or transferred by deployment. After configuring the environment variables, initialize the Neon schema with `python manage.py migrate` using the production `DATABASE_URL`. Import existing site records and media separately if they should appear online; do not commit database files, media, or secrets. Vercel redeploys when changes reach the connected branch, but this repository must first be pushed successfully to GitHub.

## Layout
`core/models.py` data · `core/views.py` public pages and orders · `core/dash.py` dashboard CRUD · `core/api.py` edit-mode saves · `core/templates/core/` pages · `core/static/core/` CSS and JS · `core/presets.py` site types.
