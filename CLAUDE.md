# Project Rules

## Responsive Design (MANDATORY)
- Every UI change must work on both desktop (>768px) and mobile (<=768px).
- When modifying or adding any HTML/CSS, always check and update the mobile media queries in `style.css` accordingly.
- Inline styles in `index.html` that define grid/flex layouts must have corresponding mobile overrides in the `@media (max-width: 768px)` block.
- Test mentally at three widths: desktop (1280px), tablet (768px), small phone (420px).

## File Structure
- `index.html` — single-page website, all content here
- `style.css` — all styles, mobile responsive rules at the bottom
- Mobile breakpoints: 768px (main), 420px (extra small)

## 数据存档

所有原始数据将存在`Embodied-R1.5.xlsx`这个文件中：
- Maniskill-PartNet: Affordance实验的数据 
- Embodied-R1.5-SFT-Dataset: SFT的使用的全部数据集和数据量
- Embodied-R1.5-RFT-Dataset: RFT的使用的全部数据集和数据量
- GeneralBenchmark: 通用视觉数据集的对比结果
- VLM-Nano：更少的模型的VLM Benchmark的对比实验，用于柱状图绘图
- VLM-Full：完整的VLM Benchmark的实验结果 
- VLM-Trace：Trace Benchmark的全部实验结果
- VLA：所有VLA相关实验Benchmark的实验结果
- Real-World：真机实验的实验结果
- Compare：对比实验的结果
