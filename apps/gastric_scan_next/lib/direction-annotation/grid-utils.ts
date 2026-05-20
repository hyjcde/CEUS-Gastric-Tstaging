import type { GridCellAnnotation } from '@/lib/direction-annotation/directionAnnotationTypes';

export const GRID_ROWS = 3;
export const GRID_COLS = 3;

export function createEmptyGrid(): GridCellAnnotation[] {
  const cells: GridCellAnnotation[] = [];
  for (let row = 0; row < GRID_ROWS; row += 1) {
    for (let col = 0; col < GRID_COLS; col += 1) {
      cells.push({
        row,
        col,
        has_breach: false,
        visible_layers: 'uncertain',
        breach_confidence: 'medium',
      });
    }
  }
  return cells;
}

export function mergeSavedGridCells(saved: GridCellAnnotation[]): GridCellAnnotation[] {
  const grid = createEmptyGrid();
  for (const cell of saved) {
    const idx = cell.row * GRID_COLS + cell.col;
    if (idx < 0 || idx >= grid.length) continue;
    grid[idx] = {
      ...grid[idx],
      ...cell,
      row: cell.row,
      col: cell.col,
      has_breach: true,
    };
  }
  return grid;
}
