"""Run on the Mini: store iCloud credentials privately without enabling delivery."""
import argparse
import getpass
import json
import os
from pathlib import Path
import tempfile


def private_write(path, text):
    path = Path(path)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name+'-')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def configure(config_path, username, password):
    config_path = Path(config_path)
    if not username.endswith('@icloud.com') or any(c.isspace() for c in username):
        raise ValueError('Use your full primary @icloud.com Mail address')
    if not password.strip():raise ValueError('An app-specific password is required')
    original = config_path.read_text()
    config = json.loads(original)
    if config.get('email_notifications',{}).get('enabled'):
        raise ValueError('Disable existing email delivery before changing providers')
    password_path = config_path.parent/'library-icloud-password'
    private_write(password_path, password.strip()+'\n')
    private_write(config_path.with_name('config.before-icloud.json'), original)
    config['email_notifications'] = dict(enabled=False,provider='icloud',
        smtp_username=username, password_file=str(password_path.resolve()),
        **{'from':'Library <library@wearyfather.org>'})
    private_write(config_path, json.dumps(config,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default=str(Path.home()/'library-access-pilot/state/config.json'))
    args=p.parse_args()
    username=input('Primary iCloud Mail address (@icloud.com): ').strip().lower()
    password=getpass.getpass('App-specific password (hidden): ')
    configure(args.config,username,password)
    print('iCloud settings saved privately. Sending is still disabled. No email was sent.')


if __name__=='__main__':main()
