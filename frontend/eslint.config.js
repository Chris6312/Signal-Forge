import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  // Ignore build output and dependencies
  { ignores: ['dist', 'node_modules'] },

  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],

    // Only lint TypeScript source files
    files: ['**/*.{ts,tsx}'],

    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },

    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },

    rules: {
      // React hooks — enforce rules of hooks and exhaustive deps
      ...reactHooks.configs.recommended.rules,

      // Vite HMR — warn when a module exports something other than components
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // TypeScript — allow explicit `any` in this codebase for gradual typing
      '@typescript-eslint/no-explicit-any': 'off',

      // TypeScript — unused vars are already caught by tsc (noUnusedLocals /
      // noUnusedParameters in tsconfig), but ESLint catches them in .tsx files
      // during editor feedback before a full build. Underscore-prefixed names
      // are treated as intentionally unused.
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
)
