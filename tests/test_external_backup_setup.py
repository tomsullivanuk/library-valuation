from copy import deepcopy
import json
import plistlib
import subprocess
import pytest
from operations.configure_external_backup import verify_disk, setup


def identity():
    plan=dict(device='/dev/disk4', size=2_000_000_000_000, media_name='Synthetic USB Disk', partition_uuid='SYNTHETIC-ID')
    info=dict(Internal=False, WholeDisk=True, VirtualOrPhysical='Physical', BusProtocol='USB',
              Writable=True, DeviceNode=plan['device'], Size=plan['size'], IORegistryEntryName=plan['media_name'])
    layout=dict(AllDisksAndPartitions=[dict(DeviceIdentifier='disk4', Partitions=[dict(DiskUUID='SYNTHETIC-ID')])])
    return plan,info,layout


def test_only_exact_external_disk_matches():
    plan,info,layout=identity()
    verify_disk(plan,info,layout)
    for key,value in [('Internal',True),('WholeDisk',False),('Size',1),
                      ('DeviceNode','/dev/disk0'),('VirtualOrPhysical','Virtual'),
                      ('Writable',False),('BusProtocol','Apple Fabric')]:
        changed=deepcopy(info);changed[key]=value
        with pytest.raises(ValueError):verify_disk(plan,changed,layout)
    layout['AllDisksAndPartitions'][0]['Partitions'][0]['DiskUUID']='CHANGED-AFTER-ERASE'
    with pytest.raises(ValueError):verify_disk(plan,info,layout)


def test_no_erase_without_explicit_flag_or_admin_access(tmp_path,monkeypatch):
    with pytest.raises(ValueError):setup(tmp_path/'absent-plan')
    monkeypatch.setattr('operations.configure_external_backup.os.geteuid',lambda:501)
    with pytest.raises(PermissionError):setup(tmp_path/'absent-plan',True)


def test_failed_disk_access_preflight_never_erases(tmp_path,monkeypatch):
    plan,info,layout=identity();plan['hostname']='Synthetic-Mini'
    path=tmp_path/'plan.json';path.write_text(json.dumps(plan))
    monkeypatch.setattr('operations.configure_external_backup.os.geteuid',lambda:0)
    def output(args,**kwargs):
        if 'scutil' in args[0]:return 'Synthetic-Mini\n'
        return plistlib.dumps(info if 'info' in args else layout)
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(1,args)
    monkeypatch.setattr('operations.configure_external_backup.subprocess.check_output',output)
    monkeypatch.setattr('operations.configure_external_backup.subprocess.run',run)
    with pytest.raises(subprocess.CalledProcessError):setup(path,True)
    assert calls==[['/usr/bin/tmutil','enable']]
