"""Import only the bay and its two movable parked craft; preserve the existing material system."""
import os
import shutil
import tempfile
import unreal
ROOT = os.environ.get('ASTRA_ROOT', '/Users/beltromatti/Desktop/ASTRA')
SRC = tempfile.mkdtemp(prefix='astra_kestrel_')
try:
    for name in ('SM_SHIP_ShuttleBay', 'SM_SHIP_KestrelParked1', 'SM_SHIP_KestrelParked2', 'SM_SHIP_KestrelDoor'):
        shutil.copyfile(ROOT + '/art/export/ship/' + name + '.fbx', SRC + '/' + name + '.fbx')
    scope = {'SRC': SRC, 'DST': '/Game/ASTRA/Kit/Ship', 'NANITE': True, '__name__': '__main__'}
    exec(compile(open(ROOT + '/tools/ue_scripts/import_kit.py').read(), 'import_kit.py', 'exec'), scope)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
finally:
    shutil.rmtree(SRC)
