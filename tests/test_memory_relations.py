import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.project_memory.hashing import sha256_text
from tools.project_memory.services import knowledge, rationale
from tools.project_memory.services.memory_relations import links_from_markdown, load_links, restore_links, relation_details


class MemoryRelationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'source.md').write_text('Observed result\n')
        (self.root / 'note.md').write_text('A decision\n')
        for module in (knowledge, rationale):
            mock = patch.object(module, '_index_entry')
            mock.start()
            self.addCleanup(mock.stop)
        self.store = knowledge._store(self.root)
        knowledge.add_knowledge(self.root, 'research', 'Target', 'note.md')
        self.link = dict(relation='supports', target={'kind': 'knowledge', 'id': 'target'},
                         source={'path': 'source.md', 'revision': sha256_text('Observed result\n')},
                         evidence=['source.md'], confidence=0.7, status='current')

    def test_roundtrip_both_kinds_update_none_and_restore(self):
        for kind, module in [('knowledge', knowledge), ('rationale', rationale)]:
            with self.subTest(kind=kind):
                kwargs = {'evidence': ['git:abc', 'https://example.org/report']} if kind == 'rationale' else {}
                result = getattr(module, 'add_' + kind)(self.root, 'decision', kind, 'note.md',
                    links=['git:abc', self.link], **kwargs)
                content = (self.root / result.path).read_text()
                self.assertEqual(links_from_markdown(content), ['git:abc', self.link])
                getattr(module, 'update_' + kind)(self.root, result.id, 'note.md')
                content = (self.root / result.path).read_text()
                self.assertEqual(links_from_markdown(content), ['git:abc', self.link])
                with self.store.connect() as conn:
                    conn.execute(f'DELETE FROM {kind}_links WHERE {kind}_id=?', (result.id,))
                restore_links(self.store, kind, result.id, content)
                self.assertEqual(load_links(self.store, kind, result.id), ['git:abc', self.link])
                if kind == 'rationale':
                    row = self.store.query('SELECT evidence_json FROM rationale_entries WHERE id=?', (result.id,))[0]
                    self.assertEqual(json.loads(row['evidence_json']), kwargs['evidence'])

    def test_invalid_batch_does_not_change_record_or_markdown(self):
        result = knowledge.add_knowledge(self.root, 'decision', 'Owner', 'note.md', links=[self.link])
        before = (self.root / result.path).read_text()
        invalid = []
        for target in ({'kind': 'knowledge', 'id': 'missing'}, {'kind': 'knowledge', 'id': 'owner'},
                       {'kind': 'file', 'id': '../outside'}, {'kind': 'file', 'id': 'missing.py'},
                       {'kind': 'domain', 'id': 'invented'}, {'kind': 'knowledge', 'id': 'target', 'project': 'other'}):
            invalid.append({**self.link, 'target': target})
        invalid.extend([{**self.link, 'confidence': float('nan')}, {**self.link, 'relation': 'invented'}])
        for link in invalid:
            with self.subTest(link=link), self.assertRaises(ValueError):
                knowledge.update_knowledge(self.root, 'owner', 'note.md', links=[self.link, link])
            self.assertEqual((self.root / result.path).read_text(), before)
            self.assertEqual(load_links(self.store, 'knowledge', 'owner'), [self.link])

    def test_source_and_target_lifecycle_are_diagnostics_not_truth(self):
        result = rationale.add_rationale(self.root, 'decision', 'Owner', 'note.md', links=[self.link])
        (self.root / 'source.md').write_text('Changed\n')
        knowledge.retire_knowledge(self.root, 'target')
        detail = relation_details(self.store, 'rationale', result.id)[0]
        self.assertEqual(detail['source_revision_status'], 'stale')
        self.assertEqual(detail['target_status'], 'archived')
        self.assertFalse(detail['verified'])
        self.assertEqual(detail['link'], self.link)

    def test_add_reads_exported_frontmatter(self):
        first = knowledge.add_knowledge(self.root, 'decision', 'First', 'note.md', links=[self.link])
        second = knowledge.add_knowledge(self.root, 'decision', 'Second', first.path)
        self.assertEqual(load_links(self.store, 'knowledge', second.id), [self.link])

    def test_restore_with_recreated_endpoints_and_changed_index(self):
        from tools.project_memory.services.index_project import index_project
        original = rationale.add_rationale(self.root, 'decision', 'Owner', 'note.md', links=[self.link])
        saved = (self.root / original.path).read_text()
        with self.store.connect() as conn:
            conn.execute('DELETE FROM rationale_entries')
            conn.execute('DELETE FROM knowledge_entries')
        knowledge.add_knowledge(self.root, 'research', 'Target', 'note.md')
        rationale.add_rationale(self.root, 'decision', 'Owner', 'note.md')
        restore_links(self.store, 'rationale', 'owner', saved)
        with patch('tools.project_memory.services.index_project.QdrantLocalStore'):
            index_project(self.root, 'changed')
        self.assertEqual(load_links(self.store, 'rationale', 'owner'), [self.link])

    def test_symlink_escape_source_domain_and_replacement(self):
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside) / 'foreign.md').write_text('Foreign')
            (self.root / 'foreign.md').symlink_to(Path(outside) / 'foreign.md')
            for link in ({**self.link, 'target': {'kind': 'file', 'id': 'foreign.md'}},
                         {**self.link, 'source': {**self.link['source'], 'path': 'foreign.md'}}):
                with self.assertRaises(ValueError):
                    rationale.add_rationale(self.root, 'decision', 'Invalid', 'note.md', links=[link])
            self.assertEqual(self.store.query("SELECT id FROM rationale_entries WHERE id='invalid'"), [])
        cfg = self.root / '.project-memory/config.yaml'
        cfg.write_text('memory:\n  classification:\n    domains: [analytics]\n')
        link = {**self.link, 'target': {'kind': 'domain', 'id': 'analytics'}}
        result = knowledge.add_knowledge(self.root, 'decision', 'Domain', 'note.md', links=[link])
        knowledge.update_knowledge(self.root, result.id, 'note.md', links=[])
        self.assertEqual(load_links(self.store, 'knowledge', result.id), [])
        self.assertEqual(links_from_markdown((self.root / result.path).read_text()), [])

    def test_restore_rejects_markdown_from_different_owner(self):
        first = knowledge.add_knowledge(self.root, 'decision', 'First', 'note.md', links=[self.link])
        knowledge.add_knowledge(self.root, 'decision', 'Second', 'note.md')
        with self.assertRaises(ValueError):
            restore_links(self.store, 'knowledge', 'second', (self.root / first.path).read_text())

    def test_add_rejects_self_file_before_overwriting_existing_note(self):
        path = self.root / '.project-memory/knowledge/decision/self-file.md'
        path.parent.mkdir(parents=True)
        path.write_text('Keep existing note')
        link = {**self.link, 'target': {'kind': 'file', 'id': path.relative_to(self.root).as_posix()}}
        with self.assertRaises(ValueError):
            knowledge.add_knowledge(self.root, 'decision', 'Self file', 'note.md', links=[link])
        self.assertEqual(path.read_text(), 'Keep existing note')
