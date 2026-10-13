# sv2cli

[English](README.md) · [完整功能清单](docs/features.md) · [批量编辑说明](docs/recipes.md)

为 Synthesizer V Studio 2 做的可复用命令行工具。检查和修复 SVP、切换声库、批量改发声参数和混音、导入导出 MIDI、渲染混音及分轨，都可以从终端运行。

工程工具支持 Windows、macOS、Linux；原生渲染使用本机安装的 VST3 乐器插件，给插件提供播放时钟和消息循环。**不依赖截图识图、鼠标坐标或键盘自动操作。** 合成仍需要你自己的已授权插件和声库。

```sh
python -m pip install ".[render,midi]"
sv2cli doctor
sv2cli inspect song.svp
sv2cli validate song.svp
sv2cli render song.svp -o mix.wav --warmup 30 --timeout 1800
```

本地真实渲染验证环境为 Windows 11、Python 3.12、SV2 2.2.1、Kasane Teto AI 2。macOS 渲染代码已实现，尚待真实插件验证；Linux 可用工程工具和自定义命令后端。不同 Python 版本的渲染能力取决于 DawDreamer 是否提供对应安装包。

## 换声库与调音色

```sh
sv2cli voice song.svp --track "#1" --name "Kasane Teto AI 2" -o teto.svp
sv2cli voice teto.svp --track "#1" --language-override mandarin -o teto-zh.svp
sv2cli voice teto-zh.svp --track "#1" --params @examples/male-voice.json -o male.svp
sv2cli mixer male.svp --track "#1" --gain -3 --pan 0.2 -o mixed.svp
sv2cli diff song.svp mixed.svp --summary
```

声部可用精确名称或 `#1`、`#2` 选择，`--track` 可以重复；省略则处理所有声部。切换声库时同时处理轨道默认声库和组内覆盖，避免某些组仍然用旧声库。加 `--inherit` 可让组继承轨道声库。

默认声库字段为 SV2 日语、SVR3、201、romaji；其他声库可指定 `--database-version`、`--language`、`--phoneset`、`--backend`。缓存声库目录不等于已安装或已激活，`voices` 会明确标注。跨语言切换保留原歌词和音素；要改音素，需要明确进行谱面编辑。

参数文件可设置 Gender、Tone Shift、气声、张力、Vocal Mode、合唱人数等。`examples/male-voice.json` 只是通用示例，不是经过试听的最佳音色。

## 锁谱与批处理

```sh
sv2cli edit song.svp --recipe examples/choral-mix.json --score-lock -o choir.svp
sv2cli edit song.svp --recipe examples/choral-mix.json --dry-run -o preview.svp
sv2cli notes song.svp --track "#1" -o notes.json
sv2cli convert midi-out song.svp -o song.mid
sv2cli render song.svp --stems -o stems --bit-depth 24
sv2cli capabilities
```

所有写操作另存，默认不覆盖已有输出；即使指定 `--force`，也不能覆盖输入 SVP。配方在副本上执行，失败不写结果。未知工程字段保留，共享的音符组采用复制后再修改，避免改一个声部牵连另一个。

改音高、节奏、歌词、音素、速度和结构需要 `--allow-score-changes`。`--score-lock` 会核对这些字段是否保持一致；发声参数和音高曲线仍会影响实际演唱，不能把锁谱检查当成听感验证。

渲染支持超时、取消、单声部、分轨、单/双声道和 PCM16/24。会检查空文件、静音、时长、应发声的时间窗、能量稳定性与削波。结果附带 JSON 报告，失败保留日志。分轨文件使用 `01.wav` 等编号，报告保存原声部名称。

## 多环境与实时接口

使用配置保存不同机器的插件路径：

```sh
sv2cli config set --name studio --value @examples/profile.json
sv2cli --profile studio doctor
```

工程编辑与 VST3 渲染不需要启动 Studio 脚本。读取当前编辑器的计算音素、音高、播放控制或生成 Retake，可安装可选 Lua bridge；安装后在 Studio 里重扫脚本并启动一次。详情见 [实时 API](docs/live.md)。

已经逐类核对功能范围，见 [功能清单](docs/features.md)。购买激活、下载声库、Full ARA、原生分离气声音频、Voice-to-MIDI、MusicXML 导入仍由 Studio 提供。工具不包含引擎、声库或授权文件。
