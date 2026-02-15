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
