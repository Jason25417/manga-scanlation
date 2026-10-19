# manga-scanlation

**把一整个文件夹的漫画图片丢进去，拿回来的是同样这些图，只是原文已经抠掉、背景补好、换成了另一种语言的译文。**

一个文件夹就是一本。二十本丢进去，敲一条命令就能走开；回来时每个文件夹里都是翻译好的页面。它是给那种「手里堆着一批没汉化的本子、又完全不想一页一页去改气泡」的人做的。

装好之后用起来只有三步：把书文件夹放进 `data/source/`，把 `config.example.yaml` 复制成 `config.yaml` 填上你的翻译模型，先跑 `mscan doctor` 把环境问题挑出来，再跑 `mscan run` 处理所有没做完的书。重复跑 `mscan run` 永远安全：它跳过已经翻完的页，所以半夜被中断的那一批会从断点接着做，而不是从头再来。

```bash
mscan doctor          # 环境正常吗？
mscan run             # 处理所有待翻的书
mscan compare         # 每本出一张图：原图旁边放译文
```

---

## 它到底做了什么

每一页都会依次发生四件事：

1. **找字。** 检测器把每一块文字区域框出来 —— 气泡里的对白、直接压在画上的拟声词、页边注。
2. **抹掉。** inpainting 模型把原文擦掉，再用周围画面把洞补上，不留原来的字形残影。
3. **翻译。** 这些行连同上下文一起交给语言模型（或者 DeepL、Sakura、本地模型 —— 你选），这样人称和专名在整章里保持一致。
4. **嵌字。** 译文被画回原来的文字区域，沿用原来的对齐方式、加描边保证可读、字号自动适配文字框。

所有东西都是磁盘上的文件夹。没有数据库、没有服务进程、没有你用文件管理器看不见的状态。

## 这个仓库是什么、不是什么

这是**精简核心**：管道本体、配置层、素材源适配器，以及几个提高效率的小工具。它的体量刻意控制在一个下午能从头读到尾的程度。

它**不包含**原作者在一台专用机器上、为了几千本规模的库而写的那套东西：多车道并行调度器、带实时进度的网页仪表盘、渲染任务之间的显卡仲裁、通宵看门狗。那部分代码高度依赖单机工作流，诚实地说没法对外支持。更完整的版本之后可能作为另一个发布单独提供；如果真有，**这个仓库仍然是受支持的起点** —— 能自己 debug 的工具，胜过读不懂的调度器。从这里开始。

## 硬件与依赖

| | |
|---|---|
| Python | 3.10 以上（本仓库） |
| [manga-image-translator](https://github.com/zyddnys/manga-image-translator) | 负责检测、OCR、抹字、嵌字 |
| 翻译后端 | 任意 OpenAI 兼容接口、Ollama、Sakura、DeepL、Gemini、Groq… |
| 中日韩字体 | 例如思源黑体、Noto Sans CJK |
| 显卡 | 强烈建议。CPU 能跑，但很慢 |

manga-image-translator 首次运行会自己下载模型（几百 MB）；如果用它的离线翻译模型，还会额外下几个 GB。

## 安装

```bash
git clone https://github.com/your-org/manga-scanlation
cd manga-scanlation
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -e .
```

然后**在它旁边**给 manga-image-translator 单独建一个环境：

```bash
git clone https://github.com/zyddnys/manga-image-translator vendor/manga-image-translator
cd vendor/manga-image-translator
python -m venv .venv        # 刻意和我们的依赖分开
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

两个环境是故意的：manga-image-translator 会锁死它自己那套很重的依赖（torch、paddle 等），混在一起是让两边同时坏掉的最快办法。

## 配置

```bash
cp config.example.yaml config.yaml
cp config/mit-config.example.json config/mit-config.json
cp config/gpt_config.example.yaml config/gpt_config.yaml
cp config/prompt/zh-CN.example.txt config/prompt/zh-CN.txt
```

`config.yaml` 只负责接线 —— 路径、用哪个引擎、用哪个翻译后端：

```yaml
engine:
  mit:
    # 你给 manga-image-translator 建的那个环境的解释器
    python: ./vendor/manga-image-translator/.venv/bin/python
    root: ./vendor/manga-image-translator
    font: ./fonts/SourceHanSansSC-Bold.otf

translation:
  translator: openai            # manga-image-translator 支持的任何后端
  target_lang: CHS              # CHS、CHT、ENG、JPN、KOR…
  model: qwen2.5:32b
  base_url: http://127.0.0.1:11434/v1
  api_key_env: OPENAI_API_KEY   # 只写变量名，密钥本身从环境变量读
```

质量参数（掩膜外扩、字号偏移、检测阈值）在 `config/mit-config.json` 里，那就是 manga-image-translator 自己的配置格式，所以**只有一个地方要调**。示例文件里每个字段都有注释说明。

## 用法

```bash
# 1. 把素材摆好：一个文件夹一本书
cp -r ~/incoming/my-book data/source/

# 2. 检查环境
mscan doctor

# 3. 开跑
mscan run

# 4. 大批量之前先看结果
mscan compare --book my-book --pages 4
```

| 命令 | 做什么 |
|---|---|
| `mscan doctor` | 检查解释器、模型权重、字体、词典、接口、磁盘空间 |
| `mscan run` | 下载（若配置了）→ 翻译 → 汇总报告 |
| `mscan translate` | 只翻译 |
| `mscan download` | 只下载，走 gallery-dl |
| `mscan compress` | 把已完成的 PNG 转成配置里的轻量格式 |
| `mscan status` | 每本书的进度表 |
| `mscan compare` | 拼一张对照图：原图 vs 译文 |
| `mscan config` | 打印解析后的最终配置 |
| `mscan run --dry-run` | 只打印将要执行的引擎命令，什么都不做 |

常用参数：`--only 书名` 只跑指定书，`--redo` 强制重做已完成的，`--limit N` 只跑 N 本，`-v` 输出调试信息。

**输出是两步的**：引擎只写无损 PNG（因为上游只允许对 JPEG 做有损质量控制），压缩成 WebP q95 是之后单独一步。这样任何一张有损图都不会成为下一步的输入。`mscan run` 会自动做这一步，也可以单独跑 `mscan compress`。

## 选翻译后端

这里没有任何一处绑死某个模型。`translation.translator` 原样传给 manga-image-translator，所以它支持的后端全都能用：

- **本地免费** —— `ollama` 或 `custom_openai`，指向 Ollama / vLLM / LM Studio。填 `base_url`、`model`，密钥随便填个非空值。
- **任意 OpenAI 兼容接口** —— `openai` + `base_url`，托管服务和公司网关都适用。
- **日中专用** —— `sakura`，如果你有那个模型。
- **传统机翻** —— `deepl`、`baidu`、`youdao`、`caiyun`。
- **不翻译** —— `none` 只抹字不嵌字，用来在不动模型的情况下测管道。

`translation.prompt` 指向一个纯文本文件，内容就是系统提示词。`config/prompt/zh-CN.example.txt` 是一份可用的简体中文提示词；它大部分篇幅都在讲两件事，而那正是实战里真正要紧的两件事：**不许压缩译文**，以及**先纠 OCR 错字再翻译**。

## 素材源

`local` 读你已有的文件夹。`gallerydl` 调用 [gallery-dl](https://github.com/mikf/gallery-dl)，那个工具支持几百个站点 —— 本仓库对任何具体图站一无所知。把链接写进 `links.txt`（一行一个）或者 `source.gallerydl.urls`，配置从 `config/gallery-dl.example.json` 起步。

要接别的东西 —— RSS、网盘、自己扫的书 —— 接缝很小：写一个把图片放成 `data/source/<书名>/` 的函数就行，管道其余部分不用动。

## 调参（来自真实素材的经验）

默认值只是起点，不是通用答案。下面四个最常需要动，而且每个都有明确的症状：

| 参数 | 位置 | 什么症状说明该动了 |
|---|---|---|
| `mask_dilation_offset` | `mit-config.json` | 原来文字的位置留了一圈淡光或色晕。往大调，直到那层发光的边被吃掉。 |
| `font_size_offset` | `mit-config.json` | 译文看着偏小、框里留白很多。 |
| `ocr.ignore_bubble` | `mit-config.json` | 只有当气泡**外面**的字确实是噪声时才动。在「台词直接压在画上」的漫画里，**调高它等于静默删掉对白**。 |
| `context_size` | `config.yaml` | 人名或人称在页与页之间漂移。 |

默认值里有两个是「反过来就是坑」的：`inpainting_precision: fp32`（半精度会让 `torch.fft` 在非 2 的幂特征图上直接报错，而且就算能跑也更慢），以及 `disable_font_border: false`（描边是补背景不完美时维持可读性的保底手段）。

**改完任何一个参数，先 `mscan translate --only 书名 --redo` 跑一本，用 `mscan compare` 看一眼，再开批量。**

## 出问题时

**输出页数少于输入页数。** 它会被记为失败，而不是假装成功。直接再跑一次即可：引擎会跳过已经产出的页，重跑只补缺口。

**原来有的字没了。** 先查 `ocr.ignore_bubble`，通常就是它。其次 `filter_text`。

**译文乱编或串味。** 调低 `temperature`，并确认提示词里有那条行数规则：输入几行就输出几行、序号必须一致。

**模型把思考过程也嵌到图上了。** 推理模型把答案包在草稿块里。加一条 `rgx_capture` 把它剥掉（见 `config/gpt_config.example.yaml`），或者换不推理的 instruct 模型。

**字显示成方块。** 字体缺中日韩字形。把 `engine.mit.font` 指向有这些字形的字体。

**太慢。** 多半跑在 CPU 上。`mscan doctor` 会告诉你它看到了什么；这个负载下显卡快 10–30 倍。

## 边界

这是翻译辅助工具，不是出版工具。它出的是尽力而为的译文 —— 提示词不差、补背景也不差，两边都仍会出错，尤其是花体字和 OCR 不友好的画面。**发出去之前自己读一遍。**

本仓库默认什么都不下载；除非你配了素材源并给了链接。真配了，就遵守站点的条款和限速；另外记住漫画的版权属于作者 —— 这个工具是给「你有权翻译的素材」和「私人研读」用的。

## 致谢

站在：[manga-image-translator](https://github.com/zyddnys/manga-image-translator)（检测 / OCR / 抹字 / 嵌字）、[gallery-dl](https://github.com/mikf/gallery-dl)（下载），以及它们带的模型。这里的配置默认值和提示词来自在一整个真实书库上跑这条管道的经验；那些经验写成配置文件里的注释而不是 wiki，这样它会跟着代码走。

## 许可

MIT，见 [LICENSE](LICENSE)。
