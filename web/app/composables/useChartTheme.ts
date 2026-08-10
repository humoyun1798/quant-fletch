// @env browser
// Lightweight Charts + ECharts 统一主题配置
// 依据: 07-前端设计.md §图表主题

export function useChartTheme() {
  // Lightweight Charts 主题
  const chartColors = {
    // K 线
    candleUp: '#EF4444',
    candleDown: '#22C45D',
    wick: '#888888',
    // 净值曲线
    equity: '#7CBC71',        // antfu green 300
    benchmark: '#88888866',   // 灰色半透明
    // 网格
    grid: '#88888822',
    // 十字光标
    crosshair: '#88888844',
    // 文字
    text: '#888888',
  }

  // Lightweight Charts 完整配置
  const lcTheme = {
    layout: {
      background: { type: 'solid' as const, color: 'transparent' },
      textColor: chartColors.text,
    },
    grid: {
      vertLines: { color: chartColors.grid },
      horzLines: { color: chartColors.grid },
    },
    crosshair: {
      vertLine: { color: chartColors.crosshair },
      horzLine: { color: chartColors.crosshair },
    },
    timeScale: {
      borderColor: chartColors.grid,
      timeVisible: true,
    },
    rightPriceScale: {
      borderColor: chartColors.grid,
    },
  }

  // ECharts 暗色主题
  const echartsDarkTheme = {
    backgroundColor: 'transparent',
    textStyle: { color: '#888' },
    axisLine: { lineStyle: { color: '#88888844' } },
    splitLine: { lineStyle: { color: '#88888822' } },
    tooltip: { backgroundColor: '#1a1a1a', borderColor: '#88888844' },
  }

  return { chartColors, lcTheme, echartsDarkTheme }
}
