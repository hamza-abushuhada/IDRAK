"use client";
import { useMemo } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { useLocale, useTx } from "@/i18n";
import { date, jd, num } from "@/lib/format";
import Chart, { PALETTE, axisStyle } from "@/components/app/Chart";
import type { Dashboard } from "./types";

export default function SalesTrendChart({ series, height = 280, animation = true }: { series: Dashboard["series"]; height?: number; animation?: boolean }) {
  const tx = useTx();
  const locale = useLocale();
  const option = useMemo<EChartsCoreOption>(() => {
    const long = series.length > 120;
    return {
      animation,
      legend: { top: 0, data: [tx("Revenue", "المبيعات"), tx("Gross profit", "الربح الإجمالي")] },
      tooltip: { trigger: "axis", valueFormatter: (v: number) => jd(v, locale) },
      xAxis: { type: "category", data: series.map((s) => date(s.d, locale, { day: "numeric", month: "short" })), ...axisStyle, splitLine: { show: false } },
      yAxis: { type: "value", ...axisStyle, axisLabel: { ...axisStyle.axisLabel, formatter: (v: number) => (v >= 1000 ? `${num(v / 1000, 1)}k` : num(v)) } },
      series: [
        { name: tx("Revenue", "المبيعات"), type: long ? "line" : "bar", data: series.map((s) => s.revenue), barMaxWidth: 18, showSymbol: false,
          itemStyle: { color: PALETTE[0], borderRadius: [3, 3, 0, 0], opacity: 0.85 }, ...(long ? { areaStyle: { color: "rgba(194,89,58,.12)" }, lineStyle: { width: 1.5 } } : {}) },
        { name: tx("Gross profit", "الربح الإجمالي"), type: "line", data: series.map((s) => s.profit), smooth: true, showSymbol: false,
          lineStyle: { width: 2.2, color: PALETTE[1] }, itemStyle: { color: PALETTE[1] } },
      ],
    };
  }, [series, tx, locale, animation]);
  return <Chart option={option} height={height} />;
}
