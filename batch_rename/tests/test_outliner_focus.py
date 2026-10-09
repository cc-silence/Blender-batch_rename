"""Native selection prerequisites and draw/event sequencing; not GUI rendering QA."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_global_rename as support
bpy=support.bpy
from batch_rename import outliner_focus as focus,id_handles,ops_tools
class Tests(support.Tests):
    def job(self):
        obj=self.object('Target');layer=bpy.context.view_layer;layer.update();layer.objects.active=obj
        id_handles.remember(obj);id_handles.remember(self.scene)
        job=focus.FocusJob(bpy.context.window,self.scene,obj,layer.name)
        self.addCleanup(job.close)
        return job,obj
    def draw(self,job,pointer=None):
        job.mark_drawn(job.window_pointer,pointer or next(iter(job.areas)),self.scene.session_uid,job.layer_name)
    def test_focus_waits_for_destination_tree_draw(self):
        job,obj=self.job()
        with patch.object(focus,'_native_focus',return_value={'FINISHED'}) as native:
            self.assertEqual(job.advance(),'WAIT');native.assert_not_called()
            for pointer in job.areas:self.draw(job,pointer)
            self.assertEqual(job.advance(),'DONE');self.assertEqual(native.call_count,len(job.areas))
        self.assertTrue(job.closed)
    def test_wrong_scene_layer_or_area_ack_is_ignored(self):
        job,obj=self.job();pointer=next(iter(job.areas))
        job.mark_drawn(job.window_pointer,pointer,0,job.layer_name)
        job.mark_drawn(job.window_pointer,pointer,self.scene.session_uid,'WrongLayer')
        job.mark_drawn(job.window_pointer,0,self.scene.session_uid,job.layer_name)
        self.assertFalse(job.ready)
    def test_native_cancelled_is_failure_not_success(self):
        job,obj=self.job();self.draw(job)
        with patch.object(focus,'_native_focus',return_value={'CANCELLED'}) as native:
            self.assertEqual(job.advance(),'FAILED');native.assert_called_once()
            self.assertEqual(job.advance(),'STALE');self.assertEqual(native.call_count,1)
        self.assertTrue(job.closed)
    def test_native_exception_cleans_up_once(self):
        job,obj=self.job();self.draw(job)
        with patch.object(focus,'_native_focus',side_effect=RuntimeError('Editor changed')):
            self.assertEqual(job.advance(),'FAILED')
        self.assertTrue(job.closed)
    def test_escape_cancels_pending_focus(self):
        job,obj=self.job()
        from types import SimpleNamespace
        proxy=SimpleNamespace(job=job)
        self.assertEqual(focus.WKNGR_OT_FocusOutliner.modal(proxy,bpy.context,SimpleNamespace(type='ESC')),{'CANCELLED'})
        self.assertTrue(job.closed)
    def test_active_object_changed_cancels_without_focusing(self):
        job,obj=self.job();other=self.object('Other');bpy.context.view_layer.objects.active=other;self.draw(job)
        with patch.object(focus,'_native_focus') as native:
            self.assertEqual(job.advance(),'STALE');native.assert_not_called()
    def test_scene_changed_cancels_without_focusing(self):
        job,obj=self.job();bpy.context.window.scene=bpy.data.scenes.new('Other');self.draw(job)
        with patch.object(focus,'_native_focus') as native:
            self.assertEqual(job.advance(),'STALE');native.assert_not_called()
    def test_deleted_target_cancels_safely(self):
        job,obj=self.job();bpy.data.objects.remove(obj);self.draw(job)
        self.assertEqual(job.advance(),'STALE')
    def test_load_history_cleanup_drops_jobs_and_hooks(self):
        job,obj=self.job();focus._jobs[job.window_pointer]=job;focus._cancel_focus_jobs()
        self.assertTrue(job.closed);self.assertFalse(focus._jobs)
    def test_background_navigation_does_not_leave_ui_jobs(self):
        obj=self.object('Target');ops_tools.locate(bpy.context,obj)
        self.assertFalse(focus._jobs);self.assertFalse(focus.request(bpy.context,obj,self.scene,bpy.context.view_layer.name))
    def test_arm_registers_ack_only_and_close_removes_once(self):
        job,obj=self.job()
        from types import SimpleNamespace
        add=unittest.mock.Mock(return_value=object());remove=unittest.mock.Mock()
        with patch.object(focus,'bpy',SimpleNamespace(types=SimpleNamespace(SpaceOutliner=SimpleNamespace(draw_handler_add=add,draw_handler_remove=remove)))):
            job.arm();add.assert_called_once();self.assertFalse(job.ready)
            job.close();job.close();remove.assert_called_once()
if __name__=='__main__':
    names=[name for name in Tests.__dict__ if name.startswith('test_')]
    try:result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Tests(name) for name in names))
    finally:support.batch_rename.unregister()
    print('FOCUS SEQUENCING RUNTIME:',bpy.app.version_string,'UI tree drawing not exercised')
    raise SystemExit(0 if result.wasSuccessful() else 1)
