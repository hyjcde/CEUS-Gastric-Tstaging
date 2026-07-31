/**
 * Meeting-driven feature-analysis checklist shown in Next workbench.
 * Sources:
 * - docs/archive_refs/meeting_notes/2026-07-12_协和会议_需求总结.md
 * - docs/archive_refs/meeting_notes/_from_reader/plans/需求说明书_详细_结合当前项目_2026-07-12.md
 * - docs/archive_refs/meeting_notes/_from_reader/plans/人机互助_后续计划_2026-07-16.md
 */

export const HUMAN_ASSIST_MEETING_BULLETS = [
  {
    id: 'G2',
    title: '无接触不报达层',
    detail: '点选不在接触弧内 → 侧栏「未接触 / 不可分期」，禁止给层号。',
  },
  {
    id: 'G1',
    title: '分层线落在胃壁带',
    detail: '橙(壁)–绿(灶)通道内画弧；禁止穿入病灶或画出胃壁。',
  },
  {
    id: 'pen',
    title: '占壁厚 / 剩余厚度',
    detail: 'penetrationAt：病灶沿法向占壁厚比例 + 剩余壁厚（px）。',
  },
  {
    id: 'layer',
    title: '达层 L1–L5 + 软 T 提示',
    detail: 'layerJudgment：由占壁厚比给出层读数与软分期提示（非病理金标准）。',
  },
  {
    id: 'echo',
    title: '像素回声分层',
    detail: 'analyzeEchoRay / analyzeChannelNeighborhood：2–5 层自适应，允许假想插层。',
  },
  {
    id: 'sign',
    title: '可见征象优先于层号口号',
    detail: '7/16 人机互助：厚度、外缘、脂肪、多帧一致性等可见征象支撑判断。',
  },
] as const;

export const HUMAN_ASSIST_ALGO_SOURCE = {
  contactGeom: 'public/vendor/human-assist/contact_geometry.js',
  layerBridge: 'public/vendor/human-assist/interactive_layer_bridge.js',
  origin: 'docs/clinical_validation/reader_study_v150 (direction_demo / interactive_video_agent)',
  meetingIndex: 'docs/archive_refs/meeting_notes/README.md',
} as const;
