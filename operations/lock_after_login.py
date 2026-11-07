"""Lock a new graphical session, requiring immediate password-on-wake first.

Run once per GUI login via LaunchAgent. Exit nonzero for launchd retry if the
session or policy is not ready. No credentials are stored or read by this tool.
"""
import os
import plistlib
import subprocess
import time


def session_state():
    result = subprocess.run(['/usr/sbin/ioreg', '-n', 'Root', '-d', '1', '-a'],
                            check=True, capture_output=True, timeout=10)
    root = plistlib.loads(result.stdout)
    if isinstance(root, list):
        root = root[0]
    sessions = root.get('IOConsoleUsers', [])
    own = any(s.get('kCGSSessionUserIDKey') == os.getuid()
              and s.get('kCGSSessionOnConsoleKey') is True
              and s.get('kCGSessionLoginDoneKey') is True for s in sessions)
    return own, root.get('IOConsoleLocked')


def main():
    policy = subprocess.run(['/usr/sbin/sysadminctl', '-screenLock', 'status'],
                            capture_output=True, text=True, timeout=10)
    if policy.returncode or 'screenLock delay is immediate' not in policy.stdout + policy.stderr:
        raise RuntimeError('Set Require password after display is turned off to Immediately before enabling automatic login.')
    for _ in range(30):
        own, locked = session_state()
        if own:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Graphical login session is not ready')
    if locked is True:
        print('Login session is already locked.', flush=True)
        return
    subprocess.run(['/usr/bin/pmset', 'displaysleepnow'], check=True, timeout=10)
    for _ in range(20):
        own, locked = session_state()
        if own and locked is True:
            print('Login session locked and verified.', flush=True)
            return
        time.sleep(1)
    raise RuntimeError('Screen-lock state could not be verified; automatic login must not be enabled until this passes.')


if __name__ == '__main__':
    main()
