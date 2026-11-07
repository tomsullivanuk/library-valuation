"""Configure an explicitly approved external disk for Mac Mini Time Machine.

Requires administrator execution and a private plan containing the inspected
disk identity. Never infer permission to erase from the drive's name alone.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess


def verify_disk(plan, info, layout):
    if not (info.get('Internal') is False and info.get('WholeDisk') is True and
            info.get('VirtualOrPhysical') == 'Physical' and
            info.get('BusProtocol') == 'USB' and
            info.get('Writable') is True and
            info.get('DeviceNode') == plan['device'] and
            info.get('Size') == plan['size'] and
            info.get('IORegistryEntryName') == plan['media_name']):
        raise ValueError('The connected disk does not match the approved external disk')
    disks = [disk for disk in layout['AllDisksAndPartitions']
             if '/dev/' + disk['DeviceIdentifier'] == plan['device']]
    if len(disks) != 1:
        raise ValueError('Approved disk is not uniquely present')
    ids = {partition.get('DiskUUID') for partition in disks[0].get('Partitions', [])}
    if not plan['partition_uuid'] or plan['partition_uuid'] not in ids:
        raise ValueError('Partition identity changed; refusing to erase')


def setup(plan_path, erase_approved=False):
    if not erase_approved:
        raise ValueError('Explicit --erase-approved-drive is required')
    if os.geteuid() != 0:
        raise PermissionError('Run this setup with sudo on the Mac Mini')
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_text())
    host = subprocess.check_output(['/usr/sbin/scutil', '--get', 'LocalHostName'], text=True).strip()
    if host != plan['hostname']:
        raise ValueError('This is not the approved Mac Mini')
    info = plistlib.loads(subprocess.check_output(['/usr/sbin/diskutil', 'info', '-plist', plan['device']]))
    layout = plistlib.loads(subprocess.check_output(['/usr/sbin/diskutil', 'list', '-plist', 'external', 'physical']))
    verify_disk(plan, info, layout)
    print('Verified approved external disk. Checking Time Machine access before erasing.', flush=True)
    # This requires Full Disk Access as well as root. Failure leaves disk intact.
    subprocess.run(['/usr/bin/tmutil', 'enable'], check=True)
    # A successful erase changes the partition UUID, preventing accidental replay.
    subprocess.run(['/usr/sbin/diskutil', 'eraseDisk', 'APFSX', 'Mini Time Machine', 'GPT', plan['device']], check=True)
    mount = '/Volumes/Mini Time Machine'
    subprocess.run(['/usr/bin/tmutil', 'setdestination', '-a', mount], check=True)
    subprocess.run(['/usr/bin/tmutil', 'enable'], check=True)
    subprocess.run(['/usr/bin/tmutil', 'startbackup'], check=True)
    subprocess.run(['/usr/bin/tmutil', 'destinationinfo'], check=True)
    subprocess.run(['/usr/bin/tmutil', 'status'], check=True)
    print('Time Machine configured and first backup requested. Backup completion still needs verification.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--erase-approved-drive', action='store_true')
    args = parser.parse_args()
    setup(args.plan, args.erase_approved_drive)
