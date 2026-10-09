"""Exercise Blender's actual Install from Disk backend in isolated preferences."""
import os
from pathlib import Path
import sys
import tempfile
import zipfile
import tomllib

archive=Path(sys.argv[-1]).resolve()
with tempfile.TemporaryDirectory(prefix='wkngr-install-',ignore_cleanup_errors=True) as temporary:
    for kind in ('CONFIG','SCRIPTS','DATAFILES','EXTENSIONS'):
        path=Path(temporary)/kind.lower();path.mkdir()
        os.environ['BLENDER_USER_'+kind]=str(path)
    import bpy
    import _bpy_restrict_state
    # Ensure the wheel tests restrict the bpy module imported by add-ons.
    _bpy_restrict_state._bpy = bpy
    import addon_utils
    from bl_pkg.cli import blender_ext
    manifest=blender_ext.pkg_manifest_from_archive_and_validate(str(archive),strict=True)
    assert not isinstance(manifest,str),manifest
    print('OFFICIAL STRICT MANIFEST PASS:',bpy.app.version_string,flush=True)
    repo=bpy.context.preferences.extensions.repos.new(name='WK Audit',module='wk_audit',
        custom_directory=str(Path(temporary)/'repository'),source='USER')
    module_name='bl_ext.'+repo.module+'.batch_rename_cn'
    if '--upgrade-original' in sys.argv:
        # Correct only the original manifest so installation reaches its original Python code.
        original=archive.parent / ('\u6279\u91cf\u6539\u4e2d\u6587.zip')
        old_package=Path(temporary)/'original-code.zip'
        with zipfile.ZipFile(original) as source,zipfile.ZipFile(old_package,'w') as target:
            for entry in source.namelist():
                data=source.read(entry)
                if entry=='blender_manifest.toml':
                    text=data.decode('utf-8').replace('permissions = []','')
                    text=text.replace('Rename NodeGroup interface sockets + material names with preset dictionary',
                        'Rename node sockets and material names')
                    data=text.encode('utf-8')
                target.writestr(entry,data)
        try:
            bpy.ops.extensions.package_install_files('EXEC_DEFAULT',filepath=str(old_package),
                repo=repo.module,enable_on_install=True)
        except RuntimeError:
            pass
        old_classes=[cls for cls in bpy.types.PropertyGroup.__subclasses__()
            if cls.__name__=='WKNGR_Settings' and 'bl_rna' in cls.__dict__]
        assert old_classes,'Original code did not reproduce the expected partial RNA registration'
        print('ORIGINAL REGISTRATION FAILURE REPRODUCED',flush=True)
    if '--upgrade-previous' in sys.argv:
        previous=archive.parent/'batch_rename-1.4.2-blender51.zip'
        assert bpy.ops.extensions.package_install_files('EXEC_DEFAULT',filepath=str(previous),
            repo=repo.module,enable_on_install=True)=={'FINISHED'}
        previous_module=sys.modules[module_name]
        assert 'filepath' not in bpy.ops.wkngr.preset_reload.get_rna_type().properties
        previous_module.preset_manager.save_preset('before_upgrade',{'keep':'Saved'})
        previous_module.scan_cache.ensure_initialized()
        legacy=bpy.data.node_groups.new('MigrationGroup','GeometryNodeTree');legacy.use_fake_user=True
        for index in range(17):bpy.context.scene.wkngr_categories.add().entries.add().target=legacy
        assert legacy.users==18
        print('PREVIOUS RELEASE INSTALLED WITH 17 CACHE USERS',flush=True)
    for attempt in range(3):
        result=bpy.ops.extensions.package_install_files('EXEC_DEFAULT',filepath=str(archive),
            repo=repo.module,enable_on_install=True)
        assert result=={'FINISHED'},result
        module=sys.modules[module_name]
        assert module.__addon_enabled__
        if '--upgrade-previous' in sys.argv:
            assert module.preset_manager.load_preset('before_upgrade')=={'keep':'Saved'}
        assert 'filepath' not in bpy.ops.wkngr.preset_reload.get_rna_type().properties
        assert bpy.ops.wkngr.preset_reload('INVOKE_DEFAULT')=={'FINISHED'}
        assert hasattr(bpy.types.Scene,'wkngr_settings')
        assert bpy.context.scene.wkngr_settings.scan_target=='BOTH'
        assert bpy.ops.wkngr.scan()=={'FINISHED'}
        if '--upgrade-previous' in sys.argv:
            assert bpy.data.node_groups['MigrationGroup'].users==1
        if attempt==0:
            if '--upgrade-original' in sys.argv:
                assert all('bl_rna' not in cls.__dict__ for cls in old_classes)
                print('ORIGINAL FAILURE TO FIXED UPGRADE PASS',flush=True)
            from importlib import import_module
            pm=import_module(module_name+'.preset_manager')
            pm.save_preset('usr',{'\u989c\u8272':'Color'})
        if attempt==0:
            import shutil,json
            sample=next(archive.parent.glob('CC_*.json'))
            shutil.copy2(sample,Path(module.__file__).parent/'presets'/sample.name)
            source_dir=Path(module.__file__).parent/'presets'
            (source_dir/'nested'/'deep').mkdir(parents=True,exist_ok=True)
            (source_dir/'default').mkdir(exist_ok=True)
            (source_dir/'nested'/'deep'/'nested.json').write_text('{"NestedKey":"NestedValue"}',encoding='utf-8')
            (source_dir/'default'/'builtin.json').write_text('{"HiddenKey":"HiddenValue"}',encoding='utf-8')
            assert bpy.ops.wkngr.preset_reload('INVOKE_DEFAULT')=={'FINISHED'}
            assert sample.stem in pm.list_presets()
            bpy.context.scene.wkngr_settings.active_preset=sample.stem
            assert bpy.ops.wkngr.preset_reload('INVOKE_DEFAULT')=={'FINISHED'}
            assert len(bpy.context.scene.wkngr_words)==17
        assert 'nested/deep/nested' in pm.list_presets()
        assert 'default/builtin' not in pm.list_presets()
        assert pm.load_translation_dictionary('usr')['HiddenKey']=='HiddenValue'
        assert pm.load_preset(sample.stem)==json.loads(sample.read_text(encoding='utf-8'))
        assert pm.load_preset('usr')=={'\u989c\u8272':'Color'}
        print('INSTALL/REINSTALL PASS',attempt+1,flush=True)
    for attempt in range(3):
        addon_utils.disable(module_name,default_set=True)
        assert not hasattr(bpy.types.Scene,'wkngr_settings')
        assert not module.reg._registered
        errors=[]
        enabled=addon_utils.enable(module_name,default_set=True,handle_error=errors.append)
        assert enabled is not None and not errors,errors
        assert hasattr(bpy.types.Scene,'wkngr_settings')
        print('DISABLE/ENABLE PASS',attempt+1,flush=True)
    index=next(i for i,item in enumerate(bpy.context.preferences.extensions.repos) if item==repo)
    assert bpy.ops.extensions.package_uninstall('EXEC_DEFAULT',repo_index=index,pkg_id='batch_rename_cn')=={'FINISHED'}
    assert not hasattr(bpy.types.Scene,'wkngr_settings')
    assert not (Path(repo.directory)/'batch_rename_cn').exists()
    print('UNINSTALL PASS',flush=True)
    print('WKNGR REAL INSTALLATION PASS:',bpy.app.version_string,flush=True)
