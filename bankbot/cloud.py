"""Single-instance cloud launcher, with a provider port and persistent account storage."""
import os
from .config import Settings


def cloud_port():
    try:port=int(os.environ.get('PORT','8080'))
    except ValueError:raise ValueError('PORT must be an integer between 1 and 65535.') from None
    if not 1<=port<=65535:raise ValueError('PORT must be an integer between 1 and 65535.')
    return port


def main():
    os.environ.setdefault('BANKBOT_DEPLOYMENT','cloud')
    settings=Settings.load()
    port=cloud_port()
    print('CampusBank: starting cloud portal with persistent account storage...',flush=True)
    from .web import create_app
    import uvicorn
    app=create_app()
    if settings.public_url:print('Public site: '+settings.public_url,flush=True)
    else:print('Generate a domain in the hosting dashboard and configure BANKBOT_PUBLIC_URL.',flush=True)
    # The provider terminates TLS. Cookie and CSRF protections use the configured
    # public origin, so no client-supplied proxy headers need to be trusted.
    uvicorn.run(app,host='0.0.0.0',port=port,workers=1,proxy_headers=False,log_level='info')


if __name__=='__main__':main()
