"""Native, offline desktop window. All save operations call the local core directly."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import queue
import threading

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT/'runtime'
# Tcl has its own environment lookup, independent of Python's -I isolation.
os.environ['TCL_LIBRARY'] = str(RUNTIME/'tcl/tcl8.6')
os.environ['TK_LIBRARY'] = str(RUNTIME/'tcl/tk8.6')
os.environ.pop('TCLLIBPATH', None)
for _name in tuple(os.environ):
    if _name.upper().startswith('TCL8_') and _name.upper().endswith('_TM_PATH'):
        os.environ.pop(_name,None)

import tkinter as tk
from tkinter import filedialog, ttk

from application import Application
from desktop_fonts import FAMILIES, register_fonts, unregister_fonts

C = {'desk':'#0D1214','dark':'#12181A','bg':'#171E21','band':'#1F282B','line':'#2A3539',
     'border':'#3C494E','moon':'#ECE8DC','ash':'#B1B9B4','muted':'#8E9895','red':'#F0705A',
     'ink':'#BE3A26','jade':'#95D3B5','amber':'#E6B45E'}
CATEGORIES = {'accessory':'饰品','weapon':'兵器','phantom':'影之武装','goods':'物品','medicine':'药品'}


def label(parent, text='', *, color='moon', bg='bg', font=None, **kwargs):
    return tk.Label(parent,text=text,bg=C.get(bg,bg),fg=C.get(color,color),
                    font=font or (FAMILIES['body'],10),**kwargs)


def native_dark_title(window):
    try:
        window.update_idletasks()
        user = ctypes.WinDLL('user32')
        user.GetParent.argtypes = [ctypes.c_void_p]
        user.GetParent.restype = ctypes.c_void_p
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p,ctypes.c_ulong,ctypes.c_void_p,ctypes.c_ulong]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        handle = user.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(handle,20,ctypes.byref(value),ctypes.sizeof(value))
    except (OSError,AttributeError):
        pass


class ItemPicker(tk.Toplevel):
    def __init__(self, owner, row, *, visible=True):
        super().__init__(owner.root)
        if not visible:
            self.withdraw()
        self.owner,self.row = owner,row
        self.selected = {item['id']:dict(id=item['id'],name=item.get('name',item['id']),
                                        category=item['category'],quantity=item.get('quantity',1))
                         for item in row['items']}
        self.catalog = owner.data.get('catalog',[])
        self.lookup = {item['id']:item for item in self.catalog}
        self.title('选择物品 · '+row['name'])
        self.configure(bg=C['bg'])
        self.geometry('800x590')
        self.minsize(680,510)
        self.transient(owner.root)
        self.columnconfigure(0,weight=1)
        self.rowconfigure(2,weight=1)
        label(self,'为“'+row['name']+'”选择要获取的物品',font=(FAMILIES['title'],16),anchor='w').grid(row=0,column=0,sticky='ew',padx=20,pady=(18,6))
        label(self,'可选任意目录物品。普通物品补到目标持有数量；已有数量保留，缺多少补多少。',color='ash',anchor='w',wraplength=730).grid(row=1,column=0,sticky='ew',padx=20,pady=(0,12))
        tables = tk.Frame(self,bg=C['bg'])
        tables.grid(row=2,column=0,sticky='nsew',padx=20)
        tables.columnconfigure(0,weight=1)
        tables.rowconfigure(1,weight=3)
        tables.rowconfigure(4,weight=2)
        self.search = tk.StringVar()
        search = ttk.Entry(tables,textvariable=self.search)
        search.grid(row=0,column=0,sticky='ew',pady=(0,6))
        self.search.trace_add('write',lambda *_:self.filter_items())
        self.items = ttk.Treeview(tables,columns=('name','category','id'),show='headings',height=7,selectmode='browse')
        for ident,text,width in (('name','物品',180),('category','类别',90),('id','ID',260)):
            self.items.heading(ident,text=text)
            self.items.column(ident,width=width,minwidth=60,anchor='w')
        self.items.grid(row=1,column=0,sticky='nsew')
        scrollbar = ttk.Scrollbar(tables,orient='vertical',command=self.items.yview)
        scrollbar.grid(row=1,column=1,sticky='ns')
        self.items.configure(yscrollcommand=scrollbar.set)
        self.items.bind('<Double-1>',lambda _event:self.add())
        controls = tk.Frame(tables,bg=C['bg'])
        controls.grid(row=2,column=0,sticky='ew',pady=8)
        label(controls,'目标持有数量',color='ash').pack(side='left')
        self.quantity = tk.StringVar(value='1')
        ttk.Spinbox(controls,from_=1,to=9999,textvariable=self.quantity,width=7).pack(side='left',padx=8)
        ttk.Button(controls,text='添加 / 更新选择',command=self.add).pack(side='left')
        label(tables,'已选物品',color='muted',anchor='w').grid(row=3,column=0,sticky='ew',pady=(4,4))
        self.chosen = ttk.Treeview(tables,columns=('name','id','quantity'),show='headings',height=4,selectmode='browse')
        for ident,text,width in (('name','物品',200),('id','ID',260),('quantity','目标数量',80)):
            self.chosen.heading(ident,text=text)
            self.chosen.column(ident,width=width,minwidth=60)
        self.chosen.grid(row=4,column=0,sticky='nsew')
        ttk.Button(tables,text='移除所选物品',command=self.remove).grid(row=5,column=0,sticky='w',pady=(6,0))
        self.message = label(self,'',color='amber',anchor='w')
        self.message.grid(row=3,column=0,sticky='ew',padx=20,pady=(6,2))
        bottom = tk.Frame(self,bg=C['bg'])
        bottom.grid(row=4,column=0,sticky='ew',padx=20,pady=(8,16))
        ttk.Button(bottom,text='本条不获取物品，只完成支线',command=lambda:self.save(True)).pack(side='left')
        ttk.Button(bottom,text='使用这些物品',style='Primary.TButton',command=self.save).pack(side='right')
        ttk.Button(bottom,text='取消',command=self.destroy).pack(side='right',padx=8)
        self.filter_items()
        self.render_chosen()
        native_dark_title(self)
        if visible:
            self.grab_set()
            search.focus_set()

    def filter_items(self):
        term = self.search.get().strip().casefold()
        self.items.delete(*self.items.get_children())
        for item in self.catalog:
            if not term or term in (item.get('name','')+' '+item['id']).casefold():
                self.items.insert('', 'end',iid=item['id'],values=(item.get('name',item['id']),CATEGORIES.get(item['category'],item['category']),item['id']))

    def render_chosen(self):
        self.chosen.delete(*self.chosen.get_children())
        for item in self.selected.values():
            self.chosen.insert('','end',iid=item['id'],values=(item['name'],item['id'],item['quantity']))

    def add(self):
        selection = self.items.selection()
        if not selection:
            self.message.configure(text='请先从目录中选一个物品。')
            return
        try:
            quantity = int(self.quantity.get())
            if not 1 <= quantity <= 9999:
                raise ValueError
        except ValueError:
            self.message.configure(text='目标数量应为 1 到 9999 的整数。')
            return
        item = self.lookup[selection[0]]
        if item['category'] != 'goods' and quantity != 1:
            self.message.configure(text='兵器、影之武装、饰品和药品按唯一物品保存，数量填 1。')
            return
        self.selected[item['id']] = dict(item,quantity=quantity)
        self.message.configure(text='')
        self.render_chosen()

    def remove(self):
        for ident in self.chosen.selection():
            self.selected.pop(ident,None)
        self.render_chosen()

    def save(self, no_items=False):
        rewards = [] if no_items else [{'id':i['id'],'quantity':i['quantity']} for i in self.selected.values()]
        if not rewards and not no_items:
            self.message.configure(text='请添加物品，或明确选择“本条不获取物品”。')
            return
        self.destroy()
        self.owner.perform('configure',{'quest_index':self.row['index'],'rewards':rewards,'no_items':no_items})


class DesktopWindow:
    def __init__(self, application=None, *, visible=True):
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (OSError,AttributeError):
            pass
        self.loaded_fonts = register_fonts()
        self.root = tk.Tk(className='PBZQuestEditor')
        if not visible:
            self.root.withdraw()
        self.root.title('影之刃零支线存档修改器')
        self.root.configure(bg=C['desk'])
        width = min(1120,max(920,self.root.winfo_screenwidth()-160))
        height = min(760,max(620,self.root.winfo_screenheight()-160))
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(900,620)
        self.application = application or Application()
        self.data = None
        self.accounts = []
        self.state = 'locate'
        self.error = ''
        self.busy = False
        self.restore_confirm = False
        self.close_after_job = False
        self.closed = False
        self.job_number = 0
        self.results = queue.Queue()
        self.game_path = tk.StringVar()
        self.account = tk.StringVar()
        self.configure_style()
        self.build()
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.bind_all('<MouseWheel>',self.scroll)
        self.poll_id = self.root.after(50,self.poll)
        native_dark_title(self.root)
        self.render()

    def configure_style(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.',font=(FAMILIES['body'],10),background=C['bg'],foreground=C['moon'])
        style.configure('TButton',background=C['bg'],foreground=C['moon'],bordercolor=C['border'],
                        padding=(12,7),lightcolor=C['border'],darkcolor=C['border'],focuscolor=C['moon'])
        style.map('TButton',background=[('active',C['line'])],foreground=[('disabled',C['muted'])])
        style.configure('Primary.TButton',font=(FAMILIES['medium'],11),background=C['moon'],foreground=C['dark'],padding=(20,11))
        style.map('Primary.TButton',background=[('disabled',C['line']),('active','#FBF8EE')],
                  foreground=[('disabled',C['muted']),('active',C['dark'])])
        style.configure('TEntry',fieldbackground=C['dark'],foreground=C['moon'],insertcolor=C['moon'],bordercolor=C['border'],padding=6)
        style.configure('TCombobox',fieldbackground=C['dark'],foreground=C['moon'],arrowcolor=C['ash'],padding=5)
        style.map('TCombobox',fieldbackground=[('readonly',C['dark'])],foreground=[('readonly',C['moon'])],selectbackground=[('readonly',C['dark'])])
        style.configure('Treeview',background=C['dark'],fieldbackground=C['dark'],foreground=C['moon'],rowheight=29,bordercolor=C['border'])
        style.configure('Treeview.Heading',background=C['band'],foreground=C['ash'],font=(FAMILIES['body'],10),padding=6)
        style.map('Treeview',background=[('selected','#344744')],foreground=[('selected',C['moon'])])
        style.configure('Vertical.TScrollbar',background=C['border'],troughcolor=C['dark'],arrowcolor=C['ash'])
        self.root.option_add('*TCombobox*Listbox.background',C['dark'])
        self.root.option_add('*TCombobox*Listbox.foreground',C['moon'])
        self.root.option_add('*TCombobox*Listbox.selectBackground',C['border'])

    def build(self):
        shell = tk.Frame(self.root,bg=C['bg'],highlightthickness=1,highlightbackground=C['border'])
        shell.pack(fill='both',expand=True,padx=12,pady=12)
        shell.columnconfigure(0,weight=1)
        shell.rowconfigure(3,weight=1)
        header = tk.Frame(shell,bg=C['dark'])
        header.grid(row=0,column=0,sticky='ew')
        label(header,'修',bg='ink',font=(FAMILIES['seal'],12),padx=4).pack(side='left',padx=(12,8),pady=7)
        label(header,'影之刃零支线存档修改器',bg='dark',color='ash').pack(side='left')
        label(header,'本地存档',bg='dark',color='muted').pack(side='right',padx=14)
        self.strip = tk.Frame(shell,bg=C['bg'],highlightthickness=1,highlightbackground=C['line'])
        self.strip.grid(row=1,column=0,sticky='ew')
        self.facts = label(self.strip,'',anchor='w')
        self.facts.pack(side='left',padx=18,pady=10)
        self.change_button = ttk.Button(self.strip,text='更换存档',command=self.change)
        self.change_button.pack(side='right',padx=(0,12),pady=5)
        self.reload_button = ttk.Button(self.strip,text='重新读取',command=lambda:self.perform('reload'))
        self.reload_button.pack(side='right',padx=6,pady=5)
        self.band = tk.Canvas(shell,height=148,bg=C['band'],highlightthickness=0)
        self.band.grid(row=2,column=0,sticky='ew')
        self.band.bind('<Configure>',lambda _event:self.paint_band())
        self.band_inner = tk.Frame(self.band,bg=C['band'])
        self.band_window = self.band.create_window(18,18,anchor='nw',window=self.band_inner)
        self.band_inner.columnconfigure(1,weight=1)
        self.seal = tk.Canvas(self.band_inner,width=76,height=82,bg=C['band'],highlightthickness=0)
        self.seal.grid(row=0,column=0,rowspan=2,padx=(0,22),sticky='w')
        self.headline = label(self.band_inner,'',bg='band',font=(FAMILIES['title'],23),anchor='w')
        self.headline.grid(row=0,column=1,sticky='sw')
        self.subtitle = label(self.band_inner,'',bg='band',color='ash',anchor='nw',justify='left',wraplength=700)
        self.subtitle.grid(row=1,column=1,sticky='nw',pady=(6,0))
        self.tally = tk.Frame(self.band_inner,bg=C['band'])
        self.tally.grid(row=0,column=2,rowspan=2,padx=(18,0),sticky='e')
        self.center = tk.Frame(shell,bg=C['dark'])
        self.center.grid(row=3,column=0,sticky='nsew')
        self.center.columnconfigure(0,weight=1)
        self.center.rowconfigure(0,weight=1)
        self.locate = tk.Frame(self.center,bg=C['dark'])
        self.locate.columnconfigure(0,weight=1)
        label(self.locate,'游戏文件夹',bg='dark',color='muted',anchor='w').grid(row=0,column=0,columnspan=3,sticky='ew',pady=(18,6))
        self.path_entry = ttk.Entry(self.locate,textvariable=self.game_path)
        self.path_entry.grid(row=1,column=0,sticky='ew',padx=(0,8))
        self.browse_button = ttk.Button(self.locate,text='选择文件夹',command=self.browse)
        self.browse_button.grid(row=1,column=1,padx=(0,8))
        self.scan_button = ttk.Button(self.locate,text='查找账号',command=self.scan)
        self.scan_button.grid(row=1,column=2)
        label(self.locate,'存档账号',bg='dark',color='muted',anchor='w').grid(row=2,column=0,columnspan=3,sticky='ew',pady=(22,6))
        self.account_choice = ttk.Combobox(self.locate,textvariable=self.account,state='readonly')
        self.account_choice.grid(row=3,column=0,columnspan=3,sticky='ew')
        self.locate_hint = label(self.locate,'选择目录后查找账号，再读取最近的自动存档。',bg='dark',color='muted',anchor='w',justify='left',wraplength=800)
        self.locate_hint.grid(row=4,column=0,columnspan=3,sticky='ew',pady=12)
        self.game_path.trace_add('write',self.path_changed)
        self.list_frame = tk.Frame(self.center,bg=C['dark'])
        self.list_frame.columnconfigure(0,weight=1)
        self.list_frame.rowconfigure(1,weight=1)
        headings = tk.Frame(self.list_frame,bg=C['dark'])
        headings.grid(row=0,column=0,sticky='ew',padx=18)
        label(headings,'支线',bg='dark',color='muted',width=33,anchor='w').pack(side='left',padx=(38,8),pady=7)
        label(headings,'对应物品',bg='dark',color='muted',anchor='w').pack(side='left')
        self.canvas = tk.Canvas(self.list_frame,bg=C['dark'],highlightthickness=0)
        self.canvas.grid(row=1,column=0,sticky='nsew')
        self.rows_frame = tk.Frame(self.canvas,bg=C['dark'])
        self.rows_window = self.canvas.create_window(0,0,anchor='nw',window=self.rows_frame)
        self.rows_frame.bind('<Configure>',lambda _event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda event:self.canvas.itemconfigure(self.rows_window,width=event.width))
        scrollbar = ttk.Scrollbar(self.list_frame,orient='vertical',command=self.canvas.yview)
        scrollbar.grid(row=1,column=1,sticky='ns')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.message_frame = tk.Frame(self.center,bg=C['dark'])
        self.message_label = label(self.message_frame,'',bg='dark',color='ash',justify='left',anchor='nw',wraplength=850)
        self.message_label.pack(fill='both',expand=True,padx=28,pady=24)
        self.progress = ttk.Progressbar(shell,mode='indeterminate')
        self.progress.grid(row=4,column=0,sticky='ew')
        self.footer = tk.Frame(shell,bg=C['bg'],highlightthickness=1,highlightbackground=C['border'])
        self.footer.grid(row=5,column=0,sticky='ew')
        self.footer.columnconfigure(0,weight=1)
        self.footer_text = label(self.footer,'',color='ash',anchor='w',justify='left',wraplength=540)
        self.footer_text.grid(row=0,column=0,sticky='ew',padx=18,pady=16)
        self.actions = tk.Frame(self.footer,bg=C['bg'])
        self.actions.grid(row=0,column=1,padx=18,pady=12)
        label(shell,'仅处理最近自动存档中的失败支线与所选物品；保存前自动备份，游戏内效果由你验收。',
              bg='dark',color='muted',font=(FAMILIES['body'],9),anchor='w',padx=18,pady=5).grid(row=6,column=0,sticky='ew')

    def paint_band(self):
        width = self.band.winfo_width()
        self.band.itemconfigure(self.band_window,width=max(300,width-36))
        self.band.delete('brush')
        # A restrained brush texture drawn locally, without image dependencies.
        for i in range(18):
            y = 130+i*0.7
            self.band.create_line(width*.28,y,width*.60,95+i,width*.92,10+i*1.5,
                                  fill=('#293336' if i%3 else '#303A3C'),width=1,smooth=True,tags='brush')
        self.band.tag_lower('brush')
        self.subtitle.configure(wraplength=max(360,width-400))

    def scroll(self,event):
        if self.root.focus_displayof() is not None and self.root.focus_displayof().winfo_toplevel() != self.root:
            return
        if self.list_frame.winfo_ismapped():
            self.canvas.yview_scroll(-int(event.delta/120),'units')

    def path_changed(self,*_):
        if self.busy:
            return
        self.accounts = []
        self.account.set('')
        self.account_choice.configure(values=[])
        self.locate_hint.configure(text='目录已更改，请重新查找账号。')
        if self.state == 'locate':
            self.render_footer()

    def browse(self):
        if self.busy:
            return
        path = filedialog.askdirectory(parent=self.root,title='选择影之刃零游戏根目录',mustexist=True)
        if path:
            self.game_path.set(path)

    def scan(self):
        self.perform('scan',{'game':self.game_path.get().strip()})

    def open_account(self):
        selected = self.account_choice.current()
        if 0 <= selected < len(self.accounts):
            self.perform('open',{'save':self.accounts[selected]['path']})

    def show_view(self,data):
        self.data = data
        self.state = 'main' if data['failed_count'] else 'empty'
        self.restore_confirm = False
        self.render()

    def change(self):
        if not self.busy:
            self.state = 'locate'
            self.restore_confirm = False
            self.render()

    def perform(self,action,payload=None):
        if self.busy:
            return
        body = dict(payload or {})
        body['generation'] = (self.data or {}).get('generation')
        if action == 'apply':
            body['source_sha256'] = self.data['source_sha256']
        self.busy = True
        self.restore_confirm = False
        self.job_number += 1
        number = self.job_number
        if action in ('open','reload'):
            self.state = 'reading'
        elif action in ('apply','restore'):
            self.state = 'running'
        self.render()
        def work():
            try:
                result = self.application.dispatch(action,body)
                self.results.put((number,action,result,None))
            except Exception as error:
                self.results.put((number,action,None,f'{type(error).__name__}: {error}'))
        threading.Thread(target=work,daemon=True,name='local-save-operation').start()

    def poll(self):
        if self.closed:
            return
        if self.poll_id:
            self.root.after_cancel(self.poll_id)
            self.poll_id = None
        try:
            while True:
                number,action,result,error = self.results.get_nowait()
                if number != self.job_number:
                    continue
                self.busy = False
                if error:
                    self.error = error
                    self.state = 'error'
                elif action == 'scan':
                    self.accounts = result['accounts']
                    self.data = None
                    values = [item['account']+'  ·  '+item['path'] for item in self.accounts]
                    self.account_choice.configure(values=values)
                    if values:
                        self.account_choice.current(0)
                    self.locate_hint.configure(text=f'找到 {len(values)} 个账号。选择后读取最近自动存档。' if values else '未找到存档，请确认游戏根目录并先在游戏内生成自动存档。')
                    self.state = 'locate'
                elif action == 'open-backup':
                    pass
                elif action == 'apply':
                    self.data = result
                    self.state = 'partial' if result['pending_count'] else 'done' if result.get('completed_count') else 'empty'
                else:
                    self.data = result
                    self.state = 'main' if result['failed_count'] else 'empty'
                if self.close_after_job:
                    self.destroy()
                    return
                self.render()
        except queue.Empty:
            pass
        self.poll_id = self.root.after(50,self.poll)

    def render(self):
        if self.closed:
            return
        data = self.data or {}
        if self.data:
            self.facts.configure(text=f"最近自动存档  {data['date']} · {data['slot']}      账号  {data['account']}      第 {int(data['cycle'])+1} 周目")
        else:
            self.facts.configure(text='最近自动存档  未读取      账号  未选择      周目  未知')
        for widget in (self.change_button,self.reload_button):
            widget.configure(state='disabled' if self.busy or not self.data else 'normal')
        for widget in (self.path_entry,self.browse_button,self.scan_button):
            widget.configure(state='disabled' if self.busy else 'normal')
        self.account_choice.configure(state='disabled' if self.busy else 'readonly')
        texts = {
            'locate':('找到你的存档','选择游戏文件夹和账号，读取最近的自动存档。','修','moon'),
            'reading':('正在读取存档','正在校验文件并读取本地任务、物品数据，首次读取可能稍久。','读','moon'),
            'running':('正在完成支线','准备任务与物品 · 验证 · 备份 · 保存并重读','修','moon'),
            'main':(f"发现 {data.get('failed_count',0)} 条失败支线",f"将获取 {data.get('item_count',0)} 件物品。未配置的条目可在列表中选择物品后一起处理。",'败','red'),
            'empty':('没有失败支线','进行中、未开始和原本已成功的任务不在处理范围内。','静','muted'),
            'done':(f"已完成 {data.get('completed_count',0)} 条支线",f"已获取 {data.get('item_count',0)} 件物品，文件重读通过。请进游戏读取此自动存档验收。",'成','jade'),
            'partial':(f"已完成 {data.get('completed_count',0)} 条，剩余 {data.get('pending_count',0)} 条",'剩余条目保持失败，原因显示在列表中；选择物品后可继续处理。','续','amber'),
            'error':('操作未完成','没有把错误当成“没有失败支线”；详细信息见下方。','止','red')}
        head,sub,seal,color = texts[self.state]
        self.headline.configure(text=head)
        self.subtitle.configure(text=sub)
        self.seal.delete('all')
        fill = C['jade'] if self.state == 'done' else C['band']
        self.seal.create_polygon(3,6,72,2,75,73,7,78,fill=fill,outline=C[color],width=2)
        self.seal.create_text(39,39,text=seal,fill=C['dark'] if self.state=='done' else C[color],font=(FAMILIES['seal'],38))
        for child in self.tally.winfo_children():
            child.destroy()
        show_list = self.data is not None and self.state in ('main','done','partial','running')
        if show_list:
            counts = {}
            for row in data['rows']:
                if row['ready']:
                    for item in row['items']:
                        if not item.get('have'):
                            category = item['category']
                            counts[category] = counts.get(category,0)+1
            for category,count in counts.items():
                frame = tk.Frame(self.tally,bg=C['band'])
                frame.pack(side='left',padx=8)
                label(frame,str(count),bg='band',font=(FAMILIES['title'],22)).pack()
                label(frame,CATEGORIES[category],bg='band',color='ash',font=(FAMILIES['body'],9)).pack()
        for frame in (self.locate,self.list_frame,self.message_frame):
            frame.grid_forget()
        if self.state == 'locate':
            self.locate.grid(row=0,column=0,sticky='nsew',padx=20)
        elif show_list:
            self.list_frame.grid(row=0,column=0,sticky='nsew')
            self.render_rows()
        else:
            self.message_label.configure(text=self.error if self.state=='error' else '读取不会改动文件。' if self.state=='reading' else '没有改动，也没有新建备份。')
            self.message_frame.grid(row=0,column=0,sticky='nsew')
        if self.busy:
            self.progress.grid()
            self.progress.start(14)
        else:
            self.progress.stop()
            self.progress.grid_remove()
        self.render_footer()

    def render_rows(self):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        for row in self.data['rows']:
            outer = tk.Frame(self.rows_frame,bg=C['dark'])
            outer.pack(fill='x')
            tk.Frame(outer,bg=C['line'],height=1).pack(fill='x')
            frame = tk.Frame(outer,bg=C['dark'])
            frame.pack(fill='x',padx=18,pady=10)
            frame.columnconfigure(1,weight=4,minsize=245)
            frame.columnconfigure(2,weight=8,minsize=300)
            completed = row.get('completed',False)
            label(frame,'成' if completed else '败',bg='jade' if completed else 'dark',color='dark' if completed else 'red',
                  font=(FAMILIES['seal'],15),width=2,relief='solid',bd=1).grid(row=0,column=0,sticky='n',padx=(0,14),pady=3)
            name = tk.Frame(frame,bg=C['dark'])
            name.grid(row=0,column=1,sticky='nw',padx=(0,12))
            label(name,row['name'],bg='dark',anchor='w',wraplength=260,justify='left',font=(FAMILIES['medium'],11)).pack(anchor='w')
            if row.get('reason'):
                label(name,row['reason'],bg='dark',color='amber',anchor='w',wraplength=260,justify='left',font=(FAMILIES['body'],9)).pack(anchor='w',pady=(3,0))
            items = tk.Frame(frame,bg=C['dark'])
            items.grid(row=0,column=2,sticky='nw')
            for item in row['items']:
                text = item.get('name',item['id'])
                if item.get('quantity',1)>1:
                    text += ' ×'+str(item['quantity'])
                if item.get('have'):
                    text += '  已有'
                elif completed:
                    text = '✓ '+text
                label(items,text,bg='band' if not item.get('have') else 'dark',
                      color='muted' if item.get('have') else 'jade' if completed else 'moon',padx=8,pady=3).pack(anchor='w',pady=(0,4))
            if not row['items']:
                label(items,'已指定不获取物品' if row.get('explicit_none') else '对应物品待选择',bg='dark',color='muted').pack(anchor='w',pady=3)
            if not completed:
                ttk.Button(items,text='调整物品' if row['ready'] else '选择要获取的物品',
                           command=lambda current=row:ItemPicker(self,current),state='disabled' if self.busy else 'normal').pack(anchor='w',pady=(3,0))
        self.canvas.yview_moveto(0)

    def action_button(self,text,command,*,primary=False,enabled=True):
        button = ttk.Button(self.actions,text=text,command=command,style='Primary.TButton' if primary else 'TButton')
        button.pack(side='left',padx=(6,0))
        button.configure(state='normal' if enabled and not self.busy else 'disabled')
        return button

    def render_footer(self):
        for child in self.actions.winfo_children():
            child.destroy()
        data = self.data or {}
        left = '读取不会改动存档。'
        if self.restore_confirm:
            left = '恢复会撤销本次备份之后的全部游戏进度。'
            self.action_button('取消',self.cancel_restore)
            self.action_button('确认恢复备份',lambda:self.perform('restore',{'confirm':True}),primary=True)
        elif self.busy:
            left = '正在处理本地文件，请稍候。' if not self.close_after_job else '正在结束当前操作，完成后关闭窗口。'
            self.action_button('正在处理…',lambda:None,primary=True,enabled=False)
        elif self.state == 'locate':
            self.action_button('读取这份存档',self.open_account,primary=True,enabled=bool(self.accounts))
        elif self.state == 'main':
            left = '开始前自动备份，只处理最近的自动存档。'
            count = data['ready_count']
            text = f'完成 {count} 条支线并获取物品' if count==data['failed_count'] else f'处理已配置的 {count} 条支线'
            self.action_button(text,lambda:self.perform('apply'),primary=True,enabled=bool(count))
        elif self.state in ('done','partial'):
            backup = data.get('backup_path')
            left = '改动前的存档已备份\n'+backup if backup else '没有可提交的变化，未写入存档。'
            if backup:
                self.action_button('打开备份文件夹',lambda:self.perform('open-backup'))
                self.action_button('恢复备份',self.ask_restore)
            if self.state=='partial':
                self.action_button('继续处理剩余条目',lambda:self.perform('apply'),primary=True,enabled=bool(data['ready_count']))
        elif self.state == 'error':
            left = '操作未完成；重新读取后可以继续。'
            self.action_button('复制错误',self.copy_error)
            self.action_button('更换存档',self.change)
            if self.data:
                self.action_button('重新读取',lambda:self.perform('reload'),primary=True)
            else:
                self.action_button('返回',self.change,primary=True)
        elif self.state == 'empty':
            left = '没有改动，也没有新建备份。'
            self.action_button('更换存档',self.change)
            self.action_button('重新读取',lambda:self.perform('reload'),primary=True)
        self.footer_text.configure(text=left,fg=C['amber'] if self.restore_confirm else C['ash'])

    def ask_restore(self):
        self.restore_confirm = True
        self.render_footer()

    def cancel_restore(self):
        self.restore_confirm = False
        self.render_footer()

    def copy_error(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.error)

    def close(self):
        if self.busy:
            self.close_after_job = True
            self.render_footer()
        else:
            self.destroy()

    def destroy(self):
        if not self.closed:
            self.closed = True
            if self.poll_id:
                self.root.after_cancel(self.poll_id)
                self.poll_id = None
            self.root.destroy()
            unregister_fonts(self.loaded_fonts)

    def mainloop(self):
        try:
            self.root.mainloop()
        finally:
            self.destroy()

    def probe(self):
        self.root.update_idletasks()
        self.root.update()
        return {'window_title':self.root.title(),'initial_state':self.state,'window_withdrawn':self.root.state()=='withdrawn',
                'native_window_handle':self.root.winfo_id(),
                'tk_patchlevel':self.root.tk.call('package','require','Tk'),
                'tcl_library':Path(self.root.tk.eval('info library')).relative_to(ROOT).as_posix(),
                'tk_library':Path(self.root.tk.eval('set tk_library')).relative_to(ROOT).as_posix(),
                'loaded_private_fonts':len(self.loaded_fonts),'application_session_open':self.application.session is not None,
                'user_tcl_module_paths_cleared':not any(name.upper()=='TCLLIBPATH' or
                    (name.upper().startswith('TCL8_') and name.upper().endswith('_TM_PATH')) for name in os.environ),
                'startup_created_local_data':self.application.local.exists(),'http_server_started':False,'browser_started':False}


def main():
    parser = argparse.ArgumentParser(description='影之刃零支线存档修改器 · 本地桌面软件')
    parser.add_argument('--verify-desktop',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--probe-stay-open',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    window = DesktopWindow(visible=args.verify_desktop is None)
    if args.verify_desktop:
        args.verify_desktop.write_text(json.dumps(window.probe(),ensure_ascii=False,indent=2),encoding='utf8')
        if not args.probe_stay_open:
            window.destroy()
            return
    window.mainloop()


if __name__ == '__main__':
    main()
