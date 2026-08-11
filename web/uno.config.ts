import { createLocalFontProcessor } from '@unocss/preset-web-fonts/local'
import {
  defineConfig,
  presetIcons,
  presetWebFonts,
  presetWind4,
  transformerDirectives,
  transformerVariantGroup,
} from 'unocss'
import { presetAnthonyDesign } from '@antfu/design/unocss'

export default defineConfig({
  theme: {
    colors: {
      primary: {
        300: '#7CBC71',
        400: '#49833E',
        600: '#396831',
        DEFAULT: '#49833E',
      },
    },
    fontSize: {
      micro: ['0.625rem', '0.875rem'],
      mini: ['0.6875rem', '1rem'],
      compact: ['0.8125rem', '1.125rem'],
    },
  },
  shortcuts: [
    // z-index 命名层（preset 拦截裸 z-index，只放行此处定义的层）
    // 排序约定: z-nav < z-dropdown < z-tooltip < z-toast < z-modal-backdrop < z-modal-content < z-drawer-backdrop < z-drawer-content
    // 来源: antfu-toolchain.md §8 core-setup
    ['z-nav', 'z-[30]'],
    ['z-dropdown', 'z-[40]'],
    ['z-tooltip', 'z-[45]'],
    ['z-toast', 'z-[50]'],
    ['z-modal-backdrop', 'z-[60]'],
    ['z-modal-content', 'z-[70]'],
    ['z-drawer-backdrop', 'z-[80]'],
    ['z-drawer-content', 'z-[90]'],

    // 项目特有 shortcuts（通用 token 由 presetAnthonyDesign 提供）
    ['app-shell', 'w-screen h-screen flex flex-col of-hidden bg-base color-base font-sans'],
    ['h-nav', 'h-10'],
    ['h-tabs', 'h-8'],
    ['z-particle', 'z-0'],

    // 涨跌色 — A 股惯例：涨绿跌红，双模式同色
    ['color-up', 'color-#22C45D dark:color-#22C45D'],
    ['color-down', 'color-#EF4444 dark:color-#EF4444'],
    ['bg-up', 'bg-#22C45D dark:bg-#22C45D'],
    ['bg-down', 'bg-#EF4444 dark:bg-#EF4444'],
    ['bg-up-soft', 'bg-#22C45D10 dark:bg-#22C45D10'],
    ['bg-down-soft', 'bg-#EF444410 dark:bg-#EF444410'],
    ['border-up-soft', 'border-#22C45D20 dark:border-#22C45D20'],
    ['border-down-soft', 'border-#EF444420 dark:border-#EF444420'],
    ['border-pending', 'border-#8882/30 dark:border-#8882/30'],

    // 滚动
    ['scroll-touch', '[-webkit-overflow-scrolling:touch] [overscroll-behavior:contain]'],
  ],
  presets: [
    presetAnthonyDesign({
      primary: '#49833E',
      darkBackground: '#111',
    }),
    presetWind4(),
    presetIcons({
      scale: 1.2,
      collections: {
        ph: () => import('@iconify-json/ph/icons.json').then(m => m.default || m),
      },
    }),
    presetWebFonts({
      fonts: {
        sans: 'DM Sans:200,400,700',
        mono: 'DM Mono:400,500',
        cjk: 'Noto Sans SC:300,400,700',
      },
      processors: createLocalFontProcessor({
        fontAssetsDir: './public/assets/fonts',
        fontServeBaseUrl: '/assets/fonts',
      }),
    }),
  ],
  transformers: [
    transformerDirectives(),
    transformerVariantGroup(),
  ],
})
