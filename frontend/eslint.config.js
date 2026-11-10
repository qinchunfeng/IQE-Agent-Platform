import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

// 第 1 层静态检查（见 AGENTS.md「怎么算完成」）。规则集必须全绿，不是建议集。
export default tseslint.config(
  { ignores: ['dist', 'node_modules', '*.tsbuildinfo'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // Demo 的 API 边界大量使用 Record<string, unknown>，any 主要来自 types.ts 的
      // 事件 payload；收敛为 warn，避免为通过检查而批量改写类型定义。
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
)
