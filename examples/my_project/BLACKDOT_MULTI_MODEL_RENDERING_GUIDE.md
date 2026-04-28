# 多模型黑点缺陷渲染交付说明

本文档说明当前黑点缺陷生成脚本的环境、使用方式、案例图片和交付注意事项。模型资产不提交到 GitHub，后续由网盘单独提供，拉取代码后放到指定路径即可运行。

## 一、GitHub 提交范围

本次建议提交到 GitHub 的内容：

- `examples/my_project/reference_blend_blackdot_multi_model.py`
- `examples/my_project/BLACKDOT_MULTI_MODEL_RENDERING_GUIDE.md`
- `examples/my_project/blackdot_showcase_cases/`
- `.gitignore`
- `.gitattributes`

不提交到 GitHub 的内容：

- `assets/models/*.blend`
- `assets/models/*.stl`
- `blender_bin/`
- 批量渲染输出目录，例如 `UNIFIED_BLACKDOT_SHOWCASE_4MODELS_FRONT_BACK_3X/`
- 历史实验输出、训练输出、缓存目录、`.torch_cache*`
- `*.blend1`

原因：模型和完整输出体积较大，不适合放普通 Git 历史。模型资产请通过网盘提供；完整渲染结果如需共享，也建议放网盘或 GitHub Release 附件。

## 二、模型资产放置位置

拉取仓库后，请从网盘下载模型资产，并放到：

```text
assets/models/
```

脚本需要以下文件：

```text
assets/models/moxing2.blend
assets/models/moxing1_test.blend
assets/models/P101040.stl
assets/models/QC7-1336-white.blend
assets/models/QC7-5236.stl
```

用途对应关系：

| 模型参数 | 需要资产 |
| --- | --- |
| `P101040_blue` | `moxing2.blend`, `P101040.stl` |
| `QC71336_white` | `moxing2.blend`, `QC7-1336-white.blend` |
| `QC71336_gray` | `moxing2.blend`, `QC7-1336-white.blend` |
| `QC75244_white` | `moxing1_test.blend`, `QC7-5236.stl` |

## 三、环境说明

推荐环境：

- Windows 10/11
- Python 3.8+，当前测试环境使用 Python 3.10
- BlenderProc 仓库源码
- Blender 4.2.1 LTS
- NVIDIA GPU 可选但推荐；当前测试机器使用 `NVIDIA GeForce RTX 3070 Laptop GPU`

在仓库根目录安装 Python 依赖：

```powershell
python -m pip install -e .
python -m pip install pillow
```

如需运行训练或评估脚本，再安装：

```powershell
python -m pip install -r examples/my_project/requirements_eval.txt
```

脚本会优先启用 Cycles GPU 渲染，按以下顺序尝试：

```text
OPTIX -> CUDA -> HIP -> ONEAPI -> METAL
```

如果找不到可用 GPU，会自动回退 CPU。实际使用设备会写入输出目录的 `metadata.json`。

## 四、脚本用途

脚本路径：

```text
examples/my_project/reference_blend_blackdot_multi_model.py
```

该脚本是单文件整合版，不依赖旧的项目后端模块。支持：

| 参数值 | 含义 |
| --- | --- |
| `P101040_blue` | P101040 蓝色件 |
| `QC71336_white` | QC71336 白色件 |
| `QC71336_gray` | QC71336 灰色件 |
| `QC75244_white` | QC75244 白色件 |

当前功能：

- 黑点限制在工件正面或背面，由 `--anchor_sides` 控制。
- 黑点半径在模型预设范围内随机。
- 每张图随机扰动相机和灯光；可选扰动物体姿态。
- 输出 RGB、mask、overlay、YOLO 标签、metadata。
- mask 和 YOLO bbox 只标注主黑点，不标注局部过渡贴片。
- 可保存 `.blend` 供人工检查。

## 五、常用命令

下面命令在仓库根目录执行：

```powershell
cd E:\BlenderProject\BlenderProc
```

使用本机已有 Blender 4.2.1：

```powershell
python cli.py run --custom-blender-path "E:\BlenderProject\BlenderProc\blender_bin\blender-4.2.1-windows-x64\blender-4.2.1-windows-x64" examples/my_project/reference_blend_blackdot_multi_model.py -- --model P101040_blue --anchor_sides front --output examples/my_project/output_demo_p101040_front --num 3 --samples 64 --save_blend
```

如果其他机器已经安装 `blenderproc` 命令：

```powershell
blenderproc run examples/my_project/reference_blend_blackdot_multi_model.py -- --model P101040_blue --anchor_sides front --output examples/my_project/output_demo_p101040_front --num 3 --samples 64 --save_blend
```

四个模型正反面各生成三张：

```powershell
$root="examples/my_project/output_blackdot_showcase"
$models=@("P101040_blue","QC71336_white","QC71336_gray","QC75244_white")
$sides=@("front","back")
foreach($model in $models){
  foreach($side in $sides){
    python cli.py run --custom-blender-path "E:\BlenderProject\BlenderProc\blender_bin\blender-4.2.1-windows-x64\blender-4.2.1-windows-x64" examples/my_project/reference_blend_blackdot_multi_model.py -- --model $model --anchor_sides $side --output "$root/$model/$side" --num 3 --samples 64 --save_blend
  }
}
```

## 六、关键参数

| 参数 | 说明 |
| --- | --- |
| `--model` | 模型类型，必填 |
| `--output` | 输出目录，必填 |
| `--num` | 生成图片数量 |
| `--anchor_sides` | `front`、`back`，或同时传入 `front back` |
| `--samples` | Cycles 采样数；展示可用 32/64，正式数据建议 128/256 |
| `--seed` | 随机种子 |
| `--camera_jitter_strength` | 相机随机扰动强度，默认 `1.0` |
| `--light_jitter_strength` | 光照随机扰动强度，默认 `1.0` |
| `--object_jitter_degrees` | 工件姿态扰动角度，默认 `0.0` |
| `--black_dot_radius_min_scale` / `--black_dot_radius_max_scale` | 覆盖默认黑点半径范围 |
| `--black_dot_depth_min_scale` / `--black_dot_depth_max_scale` | 覆盖默认黑点深度范围 |
| `--save_blend` | 保存调试 `.blend` |
| `--save_blend_only_first` | 默认只保存第一张 `.blend`，避免输出过大 |

## 七、输出结构

每次运行会生成：

```text
output_dir/
  rgb/             渲染 RGB 图
  mask/            主黑点二值 mask
  overlay/         RGB + bbox 可视化
  labels_yolo/     YOLO 格式标签
  blend_debug/     调试用 .blend，通常只保留第一张
  metadata.json    参数、bbox、设备、随机扰动信息
  notes.md         运行说明摘要
```

`metadata.json` 中常用字段：

- `render_device`: 本次使用 GPU/CPU、计算后端和设备列表。
- `radius_scale_range`: 黑点半径范围。
- `depth_scale_range`: 黑点深度范围。
- `samples[].bbox.xywh`: bbox 像素坐标。
- `samples[].camera_jitter`: 每张图的相机扰动。
- `samples[].light_jitter`: 每张图的灯光扰动。

## 八、案例信息

轻量展示案例目录：

```text
examples/my_project/blackdot_showcase_cases/
```

包含：

- `UNIFIED_BLACKDOT_SHOWCASE_contact_sheet.jpg`
- `UNIFIED_BLACKDOT_SHOWCASE_bbox_zooms.jpg`
- `showcase_summary.json`

本轮测试：

- 四种模型/外观。
- 每种正面 3 张、背面 3 张。
- 总计 24 张渲染结果。
- 使用 `samples=32` 做快速展示测试。
- 渲染设备为 `GPU + OPTIX`。

结果摘要：

| 模型 | 面 | bbox 尺寸 |
| --- | --- | --- |
| `P101040_blue` | front | `10x10`, `8x7`, `7x9` |
| `P101040_blue` | back | `9x8`, `10x6`, `8x8` |
| `QC71336_white` | front | `7x8`, `7x8`, `10x8` |
| `QC71336_white` | back | `9x6`, `12x10`, `11x12` |
| `QC71336_gray` | front | `8x9`, `10x9`, `10x8` |
| `QC71336_gray` | back | `9x7`, `13x10`, `13x13` |
| `QC75244_white` | front | `8x7`, `7x8`, `4x5` |
| `QC75244_white` | back | `6x5`, `4x4`, `6x4` |

观察：

- `P101040_blue` 黑点尺寸接近旧参考批次。
- `QC71336_white` 和 `QC71336_gray` 的默认黑点范围已调大。
- `QC75244_white` 当前黑点仍相对偏小，如展示需求更强，可后续单独调大。
- 相机和灯光每张图都有随机扰动；只要缺陷保持可见，不要求与旧参考构图完全一致。

## 九、注意事项

1. 脚本第一行必须保留：

```python
import blenderproc as bproc
```

BlenderProc CLI 对脚本第一行有要求。

2. 不要直接提交模型和完整输出。

模型走网盘，完整输出走网盘或 Release。GitHub 仓库只保留脚本、说明和轻量案例图。

3. 如果 clone 后运行失败，先检查模型资产是否放在 `assets/models/`。

4. CPU 可以渲染但很慢。建议检查 `metadata.json` 里的 `render_device` 确认是否走 GPU。

5. `.blend` 保存时可能出现旧贴图路径 warning。

当前历史参考场景中存在少量旧贴图路径 warning，但不影响当前黑点渲染和 `.blend` 保存。长期交付时可逐步清理旧贴图资源。

6. 新增模型时需要重新校准。

正反面定义、相机距离、灯光、黑点半径和材质都应重新做单张检查后再批量生成。
