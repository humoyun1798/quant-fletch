import { createLocalFontProcessor } from '@unocss/preset-web-fonts/local'
import {
  defineConfig,
  presetIcons,
  presetWebFonts,
  presetWind4,
  transformerDirectives,
  transformerVariantGroup,
} from 'unocss'

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
    // 中性基础
    ['color-base', 'color-neutral-800 dark:color-neutral-200'],
    ['bg-base', 'bg-white dark:bg-#111'],
    ['bg-secondary', 'bg-#eee dark:bg-#222'],
    ['border-base', 'border-#8882'],

    // 激活态
    ['bg-active', 'bg-#8881'],
    ['color-active', 'color-primary-600 dark:color-primary-300'],
    ['border-active', 'border-primary-600/25 dark:border-primary-400/25'],

    // 动作
    ['btn-action', 'inline-flex items-center gap-2 rounded border border-base px2 py1 op75 hover:op100 hover:bg-active disabled:pointer-events-none disabled:op30!'],

    // 层级
    ['z-top-nav', 'z-60'],
    ['z-panel-content', 'z-70'],
    ['z-particle', 'z-0'],
    ['z-glow', 'z-1'],

    // 透明度
    ['op-fade', 'op65 dark:op55'],
    ['op-mute', 'op30 dark:op25'],

    // Shell
    ['app-shell', 'w-screen h-screen flex flex-col of-hidden bg-base color-base font-sans'],
    ['h-nav', 'h-10'],
    ['h-tabs', 'h-8'],

    // 滚动
    ['scroll-touch', '[-webkit-overflow-scrolling:touch] [overscroll-behavior:contain]'],
  ],
  presets: [
    presetWind4(),
    presetIcons({ scale: 1.2 }),
    presetWebFonts({
      fonts: {
        sans: 'DM Sans:200,400,700',
        mono: 'DM Mono:400,500',
        sc: 'Noto Sans SC:300,400,700',
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
