import unittest
from hermes_muse.installation import explicit_request


class InstallationIntentTests(unittest.TestCase):
    def test_only_whole_matching_muse_imperatives_authorize(self):
        for text, operation in [
            ('Please disable Muse now.', 'disable'), ('Disable the Muse plugin!', 'disable'),
            ('请停用Muse插件', 'disable'), ('现在请帮我禁用 hermes-muse 插件。', 'disable'),
            ('Please uninstall Muse now.', 'remove'), ('Remove the hermes-muse plugin.', 'remove'),
            ('请卸载Muse插件', 'remove'), ('移除 Muse 插件。', 'remove'),
        ]:
            with self.subTest(text=text):
                self.assertTrue(explicit_request(text, operation))
                self.assertFalse(explicit_request(text, 'remove' if operation == 'disable' else 'disable'))
        for text in [
            'Please remove the obsolete draft file from this project.',
            'Do not disable Muse.', 'Please disable Muse tomorrow.',
            'How do I disable Muse?', 'Can you explain how to disable Muse?',
            '"Please disable Muse now."', '> disable Muse', 'If needed disable Muse',
            '请不要停用Muse', '请停用Muse，但现在不执行', '明天再停用Muse',
            '怎么停用Muse', '请解释“停用Muse”', '停用Muse？', '删除项目里的Muse草稿',
            'Please remove Muse from the list.', 'Disable Muse in another profile.',
        ]:
            with self.subTest(text=text):
                self.assertFalse(explicit_request(text, 'disable'))
                self.assertFalse(explicit_request(text, 'remove'))
