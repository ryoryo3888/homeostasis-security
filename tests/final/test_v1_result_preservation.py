"""Direct V1 execution must never replace a historical result."""
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import simulation


class V1ResultPreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.previous=Path.cwd();os.chdir(self.temp.name)
        self.addCleanup(os.chdir,self.previous)

    def test_existing_result_stops_before_credentials_or_model_for_both_modes(self):
        for live,name in ((True,'simulation_result_independent_agents_no_hotline.json'),
                          (False,'simulation_result_development.json')):
            with self.subTest(live=live):
                path=Path(name);before=b'{"historical":"preserve exact bytes"}\n';path.write_bytes(before)
                with patch.object(simulation,'USE_GEMINI',live), \
                     patch.object(simulation,'getpass',side_effect=AssertionError('no credentials')) as ask, \
                     patch.object(simulation.genai,'Client',side_effect=AssertionError('no client')) as client, \
                     patch.object(simulation,'mock_decisions',side_effect=AssertionError('no fixture run')) as mock:
                    with self.assertRaises(FileExistsError): simulation.main()
                    ask.assert_not_called();client.assert_not_called();mock.assert_not_called()
                self.assertEqual(path.read_bytes(),before)

    def test_dangling_output_symlink_is_not_followed(self):
        path=Path('simulation_result_independent_agents_no_hotline.json')
        path.symlink_to('missing-result.json')
        with patch.object(simulation,'USE_GEMINI',True), \
             patch.object(simulation,'getpass',side_effect=AssertionError('no credentials')):
            with self.assertRaises(FileExistsError): simulation.main()
        self.assertTrue(path.is_symlink())
        self.assertFalse(Path('missing-result.json').exists())

    def test_racing_publisher_keeps_its_result(self):
        path=Path('result.json');original_link=os.link
        before=b'{"other_completed_run":true}\n'
        def race(source,destination):
            Path(destination).write_bytes(before)
            return original_link(source,destination)
        with patch.object(simulation.os,'link',side_effect=race):
            with self.assertRaises(FileExistsError):
                simulation.save_result_exclusive(path,{'new':'result'})
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(list(Path('.').iterdir()),[path])

    def test_failed_serialization_leaves_no_partial_result(self):
        path=Path('result.json')
        def fail(_data,stream,**_kwargs):
            stream.write('{"partial":')
            raise OSError('synthetic write failure')
        with patch.object(simulation.json,'dump',side_effect=fail):
            with self.assertRaises(OSError): simulation.save_result_exclusive(path,{'new':'result'})
        self.assertFalse(path.exists())
        self.assertEqual(list(Path('.').iterdir()),[])

    def test_success_preserves_existing_json_encoding_and_cannot_replace(self):
        path=Path('result.json');data={'日本語':'内容','values':[1,2]}
        simulation.save_result_exclusive(path,data)
        expected=io.StringIO();simulation.json.dump(data,expected,ensure_ascii=False,indent=2)
        self.assertEqual(path.read_text(),expected.getvalue())
        with self.assertRaises(FileExistsError): simulation.save_result_exclusive(path,{'replace':True})
        self.assertEqual(path.read_text(),expected.getvalue())
        self.assertEqual(list(Path('.').iterdir()),[path])


if __name__ == '__main__': unittest.main()
