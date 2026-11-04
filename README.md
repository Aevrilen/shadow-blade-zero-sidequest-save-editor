# 影之刃零支线存档修改器

Windows 桌面工具，用于查看失败的支线任务、选择物品并将配置提交到游戏存档。发行包包含独立的 EXE 和运行所需文件，支持 Windows 10/11 x64。

## 使用

1. 从 Releases 下载 ZIP，完整解压到可写文件夹，双击 `影之刃零支线存档修改器.exe`。
2. 选择包含 `platform/steam/PBZ.exe` 的游戏根目录，查找并选择账号，读取存档。
3. 为失败支线选择物品，或选择只完成支线，然后点击底部主按钮提交。写入前退出游戏。
4. 软件在 `.local/backups/` 保留备份；可通过窗口打开备份目录或恢复本次备份。

## 存档位置与导入

存档位于游戏根目录下 `ProjectPBZ/Saved/SaveGames/Steam/<账号>/PBZSaveGame.sav`。在软件中选择游戏根目录，点击“查找账号”，选择账号后点击“读取这份存档”；软件会读取最近的自动存档。

## 实现方式

程序基于 PBZ Editor 的提交 `5fdb13483cefde94e6a2f3dba3d258c84e747582`。`desktop_ui.py` 使用 Tk 提供原生窗口，`application.py` 直接调用本地操作层；`quest_editor.py`、`quest_resources.py` 和 `quest_flow_mapping.py` 处理支线与物品。`pbz_editor/` 提供存档与游戏资源读取能力，`native/` 包含开源解码器及其 Rust 源码。原生启动器源码位于 `launcher/launcher.c`，通过随包的 `runtime/pythonw.exe` 启动桌面程序。

## 构建

仓库包含现有 Windows x64 运行时、依赖和资源。在 Windows 上使用已安装的 MSVC C++ 工具和 Windows SDK 重编启动器并打包：

```powershell
.\runtime\python.exe -I -B -X utf8 tools/build_launcher.py
.\runtime\python.exe -I -B -X utf8 tools/package.py
```

生成的 ZIP 位于 `dist/`。运行测试：

```powershell
.\runtime\python.exe -I -B -X utf8 -m unittest discover -s tests -v
```

## 许可

应用及复用源码遵循 [MIT License](LICENSE)。第三方组件和字体的许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `legal/`。
