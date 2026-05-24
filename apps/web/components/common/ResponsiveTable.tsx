"use client";

import { type ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

export interface Column<T> {
  /** 列 key（用于 key 与卡片模式 label） */
  key: string;
  /** 列头展示文本 */
  header: ReactNode;
  /** 取值函数 */
  cell: (row: T) => ReactNode;
  /** 卡片模式下是否隐藏（如纯操作列） */
  hideInCard?: boolean;
  /** 卡片模式下是否作为标题（默认取第一列） */
  isCardTitle?: boolean;
  /** 桌面表格列宽 className */
  className?: string;
}

interface ResponsiveTableProps<T> {
  data: T[];
  columns: Column<T>[];
  /** 行点击跳转或操作 */
  onRowClick?: (row: T) => void;
  /** 数据为空时显示 */
  emptyState?: ReactNode;
  /** 用于卡片模式的 row key */
  rowKey: (row: T) => string | number;
  className?: string;
}

/**
 * 响应式表格：
 * - lg 及以上：渲染为标准 table
 * - 以下：每行渲染为一张 Card
 */
export function ResponsiveTable<T>({
  data,
  columns,
  onRowClick,
  emptyState,
  rowKey,
  className,
}: ResponsiveTableProps<T>) {
  if (data.length === 0) {
    return (
      <div
        className={cn(
          "text-muted-foreground rounded-lg border border-dashed p-8 text-center",
          className,
        )}
      >
        {emptyState ?? "暂无数据"}
      </div>
    );
  }

  return (
    <div className={className}>
      {/* 桌面表格 */}
      <div className="hidden lg:block">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((col) => (
                <TableHead key={col.key} className={col.className}>
                  {col.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row) => (
              <TableRow
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={onRowClick ? "cursor-pointer" : undefined}
              >
                {columns.map((col) => (
                  <TableCell key={col.key} className={col.className}>
                    {col.cell(row)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* 移动 / 平板卡片 */}
      <div className="space-y-3 lg:hidden">
        {data.map((row) => {
          const titleCol = columns.find((c) => c.isCardTitle) ?? columns[0];
          const restCols = columns.filter((c) => c !== titleCol && !c.hideInCard);
          return (
            <Card
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cn(onRowClick && "active:bg-muted/50 cursor-pointer")}
            >
              <CardContent className="space-y-2 p-4">
                <div className="text-base font-medium">{titleCol.cell(row)}</div>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
                  {restCols.map((col) => (
                    <Row key={col.key} label={col.header}>
                      {col.cell(row)}
                    </Row>
                  ))}
                </dl>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-foreground">{children}</dd>
    </>
  );
}
