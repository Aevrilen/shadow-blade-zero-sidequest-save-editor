"""Visible desktop QA with synthetic data only; never opens installed game files."""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_quest_editor import container_source, slot, task
from application import Application
from desktop_ui import DesktopWindow, ItemPicker
from pbz_editor.core import PBZSContainer
from quest_editor import QuestSession, quest_key, SUCCEEDED


class QAApplication(Application):
    def __init__(self, directory, partial=False, empty=False):
        super().__init__(directory/'local')
        self.directory = directory.resolve()
        self.game = self.directory/'synthetic-game'
        self.game.mkdir()
        save = self.directory/'合成账号/PBZSaveGame.sav'
        save.parent.mkdir()
        names = ['见习医师','救死扶伤','白山秘闻','如梦棋子','再会兄长','风车','盗亦有道','无相王','小雪','头牌花旦']
        labels = ['香薰药盒','静心小葫芦','残破容器','慈母护符','胭脂盒','神机指环','屏息绑带','绝技护符','杀气头巾','舞扇']
        quests,mappings,catalog = [],{},[]
        for number,name in enumerate(names):
            path = f'/Game/PBZstory/PBZQuest/Simple/Synthetic_{number}.Synthetic_{number}_C'
            quests.append(task(path,status=SUCCEEDED if empty else 'EQuestCompletion::QC_Failed'))
            item = {'id':f'SyntheticAccessory{number}','name':labels[number],'category':'accessory','quantity':1}
            catalog.append(dict(item))
            mappings[quest_key(path)] = {'name':name,'side':True,'rewards':[item]}
        catalog += [{'id':'SyntheticGoods','name':'合成书卷','category':'goods'},
                    {'id':'SyntheticWeapon','name':'合成双剑','category':'weapon'},
                    {'id':'SyntheticPhantom','name':'合成影之武装','category':'phantom'}]
        if partial:
            mappings.pop(quest_key(quests[2]['QuestClass']))
        value = slot(quests)
        value['Inventory']['AccessoryInfos']['SyntheticAccessory1'] = {'CurrentLevel':3,'AcquiredCycle':0}
        container = PBZSContainer(bytes(range(32)))
        source = container_source(container,[('AutoSave0',value),('ManualSave1',slot()),('__Advanced__',{'LastContinueSlot':'AutoSave0'})])
        save.write_bytes(source)
        self.session = QuestSession(save,self.game,container,source,self.local).configure(mappings)
        self.session.catalog = catalog
        self.accounts = [save.resolve()]
        self.generation = 'synthetic-desktop-qa'

    def dispatch(self, action, body):
        # Even a typed/pasted real directory is ignored by this QA harness.
        assert self.session.save_path.is_relative_to(self.directory)
        if action == 'scan':
            return {'accounts':[{'path':str(self.session.save_path),'account':'合成账号'}]}
        if action in ('open','reload'):
            return dict(self.session.view(),generation=self.generation)
        if action == 'browse':
            return {'path':str(self.game)}
        return super().dispatch(action,body)


def main():
    parser = argparse.ArgumentParser(description='Desktop QA; synthetic data only')
    parser.add_argument('--state',choices=('locate','list','done','partial','empty','error'),default='list')
    parser.add_argument('--picker',action='store_true')
    args = parser.parse_args()
    base = ROOT/'.test-tmp'
    base.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='desktop-qa-',dir=base) as folder, patch('pbz_editor.core._game_processes',return_value=[]):
        app = QAApplication(Path(folder),partial=args.state=='partial',empty=args.state=='empty')
        window = DesktopWindow(application=app)
        window.root.title('影之刃零支线存档修改器 · 合成数据验收')
        if args.state=='locate':
            window.game_path.set(str(app.game))
        elif args.state in ('done','partial'):
            view = app.dispatch('apply',{'generation':app.generation,'source_sha256':app.session.source_sha256})
            window.data = view
            window.state = 'partial' if view['pending_count'] else 'done'
            window.render()
        elif args.state=='error':
            window.error = '合成读取错误：此处用于验证错误状态，没有读取真实存档。'
            window.state = 'error'
            window.render()
        else:
            window.show_view(dict(app.session.view(),generation=app.generation))
        if args.picker and window.data and window.data['rows']:
            window.root.after(150,lambda:ItemPicker(window,window.data['rows'][0]))
        window.mainloop()


if __name__ == '__main__':
    main()
