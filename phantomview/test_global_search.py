import unittest
from unittest.mock import Mock
from global_search import KnowledgeIndex
from phantomview import note_search_policy, Handler


class SearchTests(unittest.TestCase):
    def test_no_search_or_version_observation_without_authentication(self):
        handler=Handler.__new__(Handler)
        handler.authenticated=Mock(return_value=False)
        handler.send=Mock()
        handler.server=Mock()
        handler.search_request({'query':'water'})
        self.assertEqual(handler.send.call_args.args[0],401)
        handler.server.observatory.data.assert_not_called()
        handler.bot_version_request()
        self.assertEqual(handler.send.call_args.args[0],401)
        handler.server.bot_version_monitor.status.assert_not_called()

    def test_secret_values_are_not_searchable_and_excerpt_is_relevant(self):
        snapshot={'actors':[{'key':'a','id':'a','knowledge':[{'id':'x','title':'Handbook'}]}]}
        reader=Mock(return_value={'content':'Introduction '+(' '*400)+'drip irrigation. api_key=sk-abcdefghijklmnopqrstuvwx'})
        index=KnowledgeIndex()
        self.assertIn('irrigation',index.search(snapshot,'irrigation',reader)['results'][0]['text'])
        self.assertEqual(index.search(snapshot,'abcdefghijklmnopqrstuvwx',reader)['results'],[])

    def test_content_search_is_repeatable_and_excludes_confidential_notes(self):
        snapshot={'actors':[{'key':'au:actors:a','id':'a','knowledge':[
            {'id':'note1','title':'General handbook'},
            {'id':'secret','title':'Confidential','searchable':False}]}]}
        reader=Mock(return_value={'content':'The irrigation project uses aquaponics pumps.'})
        index=KnowledgeIndex()
        one=index.search(snapshot,'áquapónics',reader)
        self.assertEqual([r['key'] for r in one['results']],['note1'])
        self.assertEqual(one,index.search(snapshot,'aquaponics',reader))
        self.assertEqual(len(index.search(snapshot,'aquaponic',reader)['results']),1)
        self.assertEqual(reader.call_count,1)
        self.assertLessEqual(len(one['results'][0]['text']),260)
        snapshot['actors'][0]['searchable']=False
        self.assertEqual(index.search(snapshot,'aquaponics',reader)['results'],[])

    def test_explicit_confidential_front_matter_and_missing_notes(self):
        self.assertFalse(note_search_policy('---\nconfidential: true\n---\nprivate'))
        self.assertFalse(note_search_policy('---\nclassification: restricted\n---\nprivate'))
        self.assertTrue(note_search_policy('---\ntitle: Handbook\n---\npublic'))
        self.assertFalse(note_search_policy('---\nbroken front matter'))
        reader=Mock(side_effect=OSError)
        result=KnowledgeIndex().search({'actors':[{'key':'a','id':'a','knowledge':[{'id':'x','title':'X'}]}]},'water',reader)
        self.assertTrue(result['partial'])
        self.assertEqual(result['results'],[])


if __name__ == '__main__':
    unittest.main()
