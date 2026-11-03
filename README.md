# luhuan-report01

陆欢维护的 Codex 项目评测报告 Skill。基于本机已使用的 `project-evaluation-report-2607` 整理，保留证据驱动、结论先行的十四章结构、暗壳 AI 业务视角和 HTML 报告交付工具。

适合开源项目、AI 模型、3D/空间智能工程管线、部署可行性和案例性能成本复盘。输出包括可浏览的多文件报告、单文件 HTML，以及带来源和限制的判断。

## 安装

需要 Python 3.10 或更新版本。安装器和报告工具使用 Python 标准库，无需 API Key 或额外 Python 依赖。实际联网研究、浏览器预览、模型调用等能力由运行 Skill 的 Codex 环境提供。

### 从仓库安装

```bash
git clone https://github.com/rofen1112/luhuan-report01.git
cd luhuan-report01
python install.py --dry-run
python install.py
```

默认安装到 `$CODEX_HOME/skills/luhuan-report01`；未设置 `CODEX_HOME` 时安装到 `~/.codex/skills/luhuan-report01`。Windows 可将 `python` 换成 `py -3`。

指定 skills 的父目录：

```bash
python install.py --dest ./my-skills
```

这会创建 `./my-skills/luhuan-report01`。同名目标已存在时安装器拒绝覆盖；原有 `project-evaluation-report-2607` 目录保留。新 Skill 可在安装后的下一轮对话使用。

也可以让 Codex 的 Skill Installer 安装此路径：

```text
使用 skill-installer 安装 https://github.com/rofen1112/luhuan-report01/tree/v1.0.0/skills/luhuan-report01
```

私有仓库需要当前 GitHub 账号具备访问权限。

### 从安装包手动安装

在 [v1.0.0 Release](https://github.com/rofen1112/luhuan-report01/releases/tag/v1.0.0) 下载 `luhuan-report01-v1.0.0.zip`，核对 `SHA256SUMS`，将其中的 `luhuan-report01` 文件夹解压到 Codex 的 `skills` 目录。最终应为 `skills/luhuan-report01/SKILL.md`。

`.skill` 文件与 ZIP 内容和校验值相同，供支持该扩展名的工具分发；手动安装可按 ZIP 解压。

## 使用示例

```text
使用 $luhuan-report01 评估这个 GitHub 项目：<项目链接>。
核验代码、部署和案例结果，区分官方事实、本地实测与分析推断，
生成带证据与限制的 HTML 报告和单文件版本。
```

```text
使用 $luhuan-report01 复盘这三个任务的耗时和成本。
按任务及相关子代理统计 usage，区分缓存输入和推理输出，
列出可缩短的验证步骤；缺少记录时说明缺口，不补造 token 或费用。
```

默认沿用十四章完整报告与暗壳 AI 视角；用户指定纯通用报告或其他结构时，遵循用户要求。Ark 背景资料是待核验的历史参考，报告应重新确认时效与来源。Skill 不依赖特定 MCP 服务；所在工作区另有设计工具规则时按该规则执行。

## 文件结构

```text
skills/luhuan-report01/
  SKILL.md
  agents/openai.yaml
  references/
  assets/html-report-template/
  scripts/validate_report.py
  scripts/bundle_single_html.py
  LICENSE
install.py
scripts/package_release.py
tests/
```

## 报告工具

复制 `skills/luhuan-report01/assets/html-report-template` 作为报告起点，填入真实内容，再执行：

```bash
python skills/luhuan-report01/scripts/validate_report.py path/to/report/index.html
python skills/luhuan-report01/scripts/bundle_single_html.py path/to/report/index.html path/to/report-single.html
```

若单文件交付还需包含报告中直接链接的本地证据附件，显式启用：

```bash
python skills/luhuan-report01/scripts/bundle_single_html.py path/to/report/index.html path/to/report-single.html --embed-linked-files
```

该选项把报告目录内的链接文件嵌入单文件；启用前核对附件内容和分享范围。工具会拒绝目录外文件。结构校验可检查章节、占位符、资源路径、图片说明和部分敏感文本；内容可信度、授权、浏览器行为与视觉质量仍需单独复核。

## 验证与打包

```bash
python -m unittest discover -s tests -v
python install.py --dry-run
python scripts/package_release.py
```

产物位于 `dist/`：版本化 ZIP、`.skill` 与 `SHA256SUMS`。构建排除缓存、凭据、符号链接及未声明文件；同一版本和输入的安装包可重复构建。

仓库包含安装、拒绝覆盖、只读预检、包路径和模板打包等测试；Linux/Windows 能力差异会在测试输出中标明。

## 发布范围与许可证

此仓库只发布 Skill、模板、安装器和测试夹具。户型图、客户资料、私有业务代码、实际会话记录、账单和凭据留在各自项目中。

代码与模板采用 [MIT License](LICENSE)。报告引用的外部文字、图像、模型、代码和数据继续遵循各自权利与许可证；使用本 Skill 不自动取得这些素材的传播或训练授权。
