"""Direct local application operations; no HTTP server or browser dependency."""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
from pbz_editor.core import EditorError, sha256
from quest_editor import QuestSession
ROOT = Path(__file__).resolve().parent

class Application:
    def __init__(self, local=None):
        self.local = Path(local or ROOT / '.local')
        self.session = None
        self.generation = None
        self.accounts = []
        self.game = None
        self.last_backup = None

    def dispatch(self, action, body):
        if action == 'browse':
            from windows_folder import choose_folder
            return {'path': choose_folder()}
        if action == 'scan':
            from pbz_editor.compatibility import executable_path
            game = Path(body.get('game', '')).resolve()
            executable_path(game)
            accounts = sorted((game / 'ProjectPBZ/Saved/SaveGames/Steam').glob('*/PBZSaveGame.sav'))
            self.accounts = [p.resolve() for p in accounts if p.is_file()]
            self.game = game
            self.session = None
            self.generation = None
            self.last_backup = None
            return {'accounts': [{'path': str(p), 'account': p.parent.name} for p in self.accounts]}
        if action == 'open':
            save = Path(body.get('save', '')).resolve()
            if self.game is None or save not in self.accounts:
                raise EditorError('请先选择游戏目录，再选择找到的账号。')
            self.session = None
            self.generation = None
            session = QuestSession.open_quests(save, self.game, self.local)
            view = session.view()
            self.session = session
            self.generation = secrets.token_hex(16)
            self.last_backup = None
            return dict(view, generation=self.generation)
        if action not in ('reload', 'apply', 'restore', 'open-backup', 'configure'):
            raise EditorError('未知操作。')
        if self.session is None or body.get('generation') != self.generation:
            raise EditorError('当前读取结果已失效，请重新读取存档。')
        session = self.session
        if action == 'configure':
            key, meta = session.set_rewards(body.get('quest_index'), body.get('rewards'), body.get('no_items') is True)
            self.local.mkdir(parents=True, exist_ok=True)
            choices = {'source': session.game_signature,
                       'quests': {k: v for k, v in session.quest_index.items() if v.get('user_selected')}}
            temporary = self.local / 'user_rewards.writing'
            temporary.write_text(json.dumps(choices, ensure_ascii=False, indent=2), encoding='utf8')
            os.replace(temporary, self.local / 'user_rewards.json')
            return dict(session.view(), generation=self.generation)
        if action == 'reload':
            session.refresh()
            session.configure(session.quest_index)
            self.generation = secrets.token_hex(16)
            return dict(session.view(), generation=self.generation)
        if action == 'open-backup':
            if not self.last_backup:
                raise EditorError('此会话还没有创建备份。')
            os.startfile(str(Path(self.last_backup).parent))
            return {'ok': True}
        if action == 'restore':
            if not self.last_backup or body.get('confirm') is not True:
                raise EditorError('恢复前需明确确认放弃备份之后的进度。')
            # Reopen current data so the atomic restore checks the actual file.
            session.refresh()
            result = session.restore(self.last_backup, allow_newer=True)
            if sha256(session.save_path.read_bytes()) != result['sha256']:
                raise EditorError('恢复后的文件又发生变化，请重新读取；恢复前备份已保留。')
            session.configure(session.quest_index)
            self.last_backup = None
            self.generation = secrets.token_hex(16)
            return dict(session.view(), generation=self.generation, restored=True, result=result)
        if body.get('source_sha256') != session.source_sha256:
            raise EditorError('页面对应的源文件已变化，请重新读取。')
        before = session.view()
        result = session.apply(session.target, [])
        # apply() authenticated/decoded the candidate; also reopen the actual file.
        if sha256(session.save_path.read_bytes()) != result['sha256']:
            raise EditorError('写入后的文件又发生变化，请重新读取；自动备份已保留。')
        session.refresh()
        session.configure(session.quest_index)
        after = session.view()
        completed = {change['quest_index'] for change in result.get('changes', [])}
        # SaveSession returns a count, not its internal changes. These are exactly
        # the pre-edit ready rows because its single candidate is committed once.
        if result['operation_count']:
            completed = {row['index'] for row in before['rows'] if row['ready']}
        rows = [dict(row, completed=row['index'] in completed) for row in before['rows']]
        backup = result.get('backup_path')
        if backup:
            self.last_backup = backup
        return dict(after, rows=rows, generation=self.generation, result=result,
                    completed_count=len(completed), backup_path=self.last_backup,
                    item_count=before['item_count'] if completed else 0)

