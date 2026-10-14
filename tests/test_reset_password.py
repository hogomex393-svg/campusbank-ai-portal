"""Password recovery must preserve records and revoke only the recovered user's sessions."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from bankbot.portal_store import PortalStore,PortalError
from bankbot import reset_password


class ResetPasswordTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.root=Path(self.folder.name)
        self.store=PortalStore(self.root/'logs/portal.sqlite3')
        self.admin=self.store.register('manager','OldSyntheticPass2026','Manager')
        self.other=self.store.register('customer','OtherSyntheticPass2026','Customer')
        self.admin_token,_=self.store.new_session(self.admin,'staff')
        self.other_token,_=self.store.new_session(self.other)
        self.chat=self.store.create_chat('u:'+self.admin['id'])
        self.store.append_message(self.chat['id'],'user','演示账户原来的聊天')
        self.request=self.store.submit('u:'+self.admin['id'],'human_support',{'category':'other','subject':'恢复测试','description':'应保留这张工单'},self.chat['id'])

    def tearDown(self):self.folder.cleanup()

    def test_reset_changes_password_preserves_records_and_revokes_only_target_sessions(self):
        before=self.store.chat('u:'+self.admin['id'],self.chat['id'])
        result=self.store.reset_password('MANAGER','NewSyntheticPass2026')
        self.assertEqual(result['revoked_sessions'],1)
        with self.assertRaises(PortalError):self.store.login('manager','OldSyntheticPass2026')
        self.assertEqual(self.store.login('manager','NewSyntheticPass2026'),self.admin)
        self.assertIsNone(self.store.session(self.admin_token))
        self.assertIsNotNone(self.store.session(self.other_token))
        self.assertEqual(self.store.chat('u:'+self.admin['id'],self.chat['id']),before)
        self.assertEqual(self.store.ticket(self.request['id'])['status'],'waiting')
        with self.store.db() as db:
            row=db.execute('SELECT password_hash FROM users WHERE id=?',(self.admin['id'],)).fetchone()
        self.assertNotEqual(row['password_hash'],'NewSyntheticPass2026')

    def test_invalid_password_or_unknown_username_does_not_change_accounts(self):
        for password in ('short',' '*8,'x'*129):
            with self.assertRaises(PortalError):self.store.reset_password('manager',password)
        with self.assertRaises(PortalError):self.store.reset_password('absent','NewSyntheticPass2026')
        self.assertEqual(self.store.login('manager','OldSyntheticPass2026'),self.admin)
        self.assertIsNotNone(self.store.session(self.admin_token))

    def test_cli_requires_hidden_interactive_input_and_does_not_print_password(self):
        capture=StringIO()
        with patch.object(reset_password,'ROOT',self.root),patch('sys.stdin.isatty',return_value=True),patch.object(reset_password.getpass,'getpass',side_effect=['DifferentTestPass1','DifferentTestPass2']),redirect_stdout(capture):
            self.assertEqual(reset_password.main(['--username','manager']),1)
        self.assertEqual(self.store.login('manager','OldSyntheticPass2026'),self.admin)
        capture=StringIO()
        with patch.object(reset_password,'ROOT',self.root),patch('sys.stdin.isatty',return_value=True),patch.object(reset_password.getpass,'getpass',side_effect=['NewSyntheticPass2026']*2),redirect_stdout(capture):
            self.assertEqual(reset_password.main(['--username','manager']),0)
        self.assertNotIn('NewSyntheticPass2026',capture.getvalue())
        self.assertEqual(self.store.login('manager','NewSyntheticPass2026'),self.admin)
        with patch.object(reset_password,'ROOT',self.root),patch('sys.stdin.isatty',return_value=False),patch.object(reset_password.getpass,'getpass') as prompt,redirect_stdout(StringIO()):
            self.assertEqual(reset_password.main(['--username','manager']),1)
            prompt.assert_not_called()


if __name__=='__main__':unittest.main()
