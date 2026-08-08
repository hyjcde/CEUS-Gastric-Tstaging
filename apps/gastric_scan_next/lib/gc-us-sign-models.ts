export type GcUsSignModelSpec = {
  id: 'length' | 'thickness' | 'layer_structure' | 'morphology' | 'boundary' | 'growth_pattern' | 'serosa_change' | 'perigastric_tissue';
  labelZh: string;
  labelEn: string;
  algorithmZh: string;
  algorithmEn: string;
  networkZh: string;
  networkEn: string;
  evidenceKind: 'clinical' | 'derived' | 'proxy';
};

/**
 * Visible model ledger for the report signs.
 *
 * This deliberately distinguishes trained networks from deterministic
 * geometry or clinical-rule evidence. A proxy must not be presented as a
 * pathological layer truth.
 */
export const GC_US_SIGN_MODEL_SPECS: readonly GcUsSignModelSpec[] = [
  {
    id: 'length',
    labelZh: '肿瘤长径',
    labelEn: 'Tumor length',
    algorithmZh: '临床测量分箱与 GC-US 软评分',
    algorithmEn: 'Clinical measurement binning and GC-US soft score',
    networkZh: '无独立影像网络，病例表格输入',
    networkEn: 'No dedicated imaging network, case-table input',
    evidenceKind: 'clinical',
  },
  {
    id: 'thickness',
    labelZh: '肿瘤厚度',
    labelEn: 'Tumor thickness',
    algorithmZh: '临床测量分箱与 GC-US 软评分',
    algorithmEn: 'Clinical measurement binning and GC-US soft score',
    networkZh: '无独立影像网络，病例表格输入',
    networkEn: 'No dedicated imaging network, case-table input',
    evidenceKind: 'clinical',
  },
  {
    id: 'layer_structure',
    labelZh: '胃壁层次结构',
    labelEn: 'Wall layer structure',
    algorithmZh: 'ContactGeom 层次提示与 WallEvidenceTool SDF',
    algorithmEn: 'ContactGeom layer hint and WallEvidenceTool SDF',
    networkZh: 'YOLO11L 胃腔框加病灶 mask，无独立壁层分类头',
    networkEn: 'YOLO11L lumen box plus lesion mask, no independent wall-layer head',
    evidenceKind: 'proxy',
  },
  {
    id: 'morphology',
    labelZh: '肿瘤形态',
    labelEn: 'Tumor morphology',
    algorithmZh: 'MorphologyTool 轮廓描述子',
    algorithmEn: 'MorphologyTool contour descriptors',
    networkZh: '病灶分割网络输出 mask，无独立形态网络',
    networkEn: 'Lesion segmentation mask, no independent morphology network',
    evidenceKind: 'derived',
  },
  {
    id: 'boundary',
    labelZh: '肿瘤边界',
    labelEn: 'Tumor margin',
    algorithmZh: '方向归一化边界与不规则度代理',
    algorithmEn: 'Direction-normalized boundary and irregularity proxy',
    networkZh: '病灶分割网络输出 mask，无独立边界网络',
    networkEn: 'Lesion segmentation mask, no independent boundary network',
    evidenceKind: 'derived',
  },
  {
    id: 'growth_pattern',
    labelZh: '生长方式',
    labelEn: 'Growth pattern',
    algorithmZh: '相对胃腔方向的径向生长与连续性',
    algorithmEn: 'Lumen-relative radial growth and continuity',
    networkZh: '病灶 mask 加 YOLO11L 胃腔几何，无独立生长网络',
    networkEn: 'Lesion mask plus YOLO11L lumen geometry, no growth network',
    evidenceKind: 'proxy',
  },
  {
    id: 'serosa_change',
    labelZh: '浆膜改变',
    labelEn: 'Serosal change',
    algorithmZh: '胃壁连续性 SDF 与报告/医生显式证据',
    algorithmEn: 'Wall-continuity SDF and report or physician evidence',
    networkZh: '病灶 mask 加胃腔框，当前不是独立浆膜分类网络',
    networkEn: 'Lesion mask plus lumen box, not an independent serosal classifier',
    evidenceKind: 'proxy',
  },
  {
    id: 'perigastric_tissue',
    labelZh: '胃周组织',
    labelEn: 'Perigastric tissue',
    algorithmZh: '胃壁代理、报告文本与医生复核',
    algorithmEn: 'Wall proxy, report text, and physician review',
    networkZh: 'DINOv3 仅作区域辅助证据，暂无验证过的组织分类头',
    networkEn: 'DINOv3 is auxiliary region evidence, no validated tissue head',
    evidenceKind: 'proxy',
  },
];

export const GC_US_SIGN_MODEL_BY_ID = Object.fromEntries(
  GC_US_SIGN_MODEL_SPECS.map((spec) => [spec.id, spec]),
) as Record<GcUsSignModelSpec['id'], GcUsSignModelSpec>;
