"use client";
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, HeatmapChart, LineChart, PieChart, ScatterChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";

echarts.use([BarChart, LineChart, PieChart, HeatmapChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, VisualMapComponent,
  MarkAreaComponent, MarkLineComponent, DataZoomComponent, CanvasRenderer]);

export const PALETTE = ["#C2593A", "#6B7A3A", "#D99A2B", "#4F7C8A", "#7A4B5C", "#A9462A", "#9AA66A", "#E3B866"];
export const INK = "#2B211B", INK3 = "#8A786A", LINE = "#E2D6C3";

const baseOption = (rtl: boolean): EChartsCoreOption => ({
  color: PALETTE,
  textStyle: { fontFamily: "IBM Plex Sans, IBM Plex Sans Arabic, sans-serif", color: INK },
  grid: { left: rtl ? 12 : 8, right: rtl ? 8 : 12, top: 28, bottom: 8, containLabel: true },
  tooltip: {
    trigger: "axis", backgroundColor: "#FFFCF7", borderColor: LINE, borderWidth: 1, padding: [8, 12],
    textStyle: { color: INK, fontSize: 12 }, extraCssText: "box-shadow:0 8px 24px -12px rgba(43,33,27,.25);border-radius:10px;",
  },
  legend: { top: 0, icon: "roundRect", itemWidth: 10, itemHeight: 10, textStyle: { color: INK3, fontSize: 12 } },
});

export const axisStyle = {
  axisLine: { lineStyle: { color: LINE } }, axisTick: { show: false },
  axisLabel: { color: INK3, fontSize: 11 }, splitLine: { lineStyle: { color: "#EFE6D8", type: "dashed" as const } },
};

export default function Chart({ option, height = 260, className, onClick }: { option: EChartsCoreOption; height?: number; className?: string; onClick?: (p: any) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const inst = useRef<echarts.ECharts | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    inst.current = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const ro = new ResizeObserver(() => inst.current?.resize());
    ro.observe(ref.current);
    return () => { ro.disconnect(); inst.current?.dispose(); inst.current = null; };
  }, []);
  useEffect(() => {
    const rtl = typeof document !== "undefined" && document.documentElement.dir === "rtl";
    inst.current?.setOption({ ...baseOption(rtl), ...option }, true);
  }, [option]);
  useEffect(() => {
    if (!inst.current || !onClick) return;
    inst.current.on("click", onClick);
    return () => { inst.current?.off("click"); };
  }, [onClick]);
  return <div ref={ref} style={{ height }} className={className} dir="ltr" />;
}
