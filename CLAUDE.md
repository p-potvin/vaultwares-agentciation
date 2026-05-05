# VaultWares Theming Skill — Claude Code Format

This project enforces VaultWares theming and design-token rules across all code and UI. You MUST:
- Use only named tokens for all colors, fonts, and spacing (see `skills/vault-designer/SKILL.md`)
- Never hardcode hex, px, or font values
- For Python/Qt: use `VaultThemeManager` and helpers
- For React/Tailwind: use `Brand/tokens.ts` and Tailwind classes
- For WinUI3/XAML: use `VaultWares.Brand.xaml` resources
- All UI must meet accessibility (WCAG AA) and i18n requirements

See `skills/vault-designer/SKILL.md` for full details, usage patterns, and token role table.
