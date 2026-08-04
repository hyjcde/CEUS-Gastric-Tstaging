import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const PIPELINE_STEPS = [
  'triage',
  'frame_extract',
  'quality',
  'binary_gate',
  'lumen_detect',
  'lesion_seg',
  'morphology',
  't_staging',
  'wall_evidence',
  'dinov3_seg',
  'dino_sign_fusion',
  'case_rag',
  'report_synth',
  'clinical_decision',
];

export async function GET() {
  return NextResponse.json({
    ok: true,
    schema_version: 'agent_result_v2',
    belief_state_schema_version: 'case_belief_state_v1',
    runtime_version: 'gastric-agent-next-scientific-loop-v1',
    orchestrator: 'langgraph_case_pipeline',
    pipeline_steps: PIPELINE_STEPS,
    capabilities: {
      lumen_detection: true,
      sam_interactive: true,
      dino_segmentation: true,
      dino_sign_fusion_evidence: true,
      benign_malignant_gate: true,
      t_staging: true,
      wall_evidence: true,
      case_rag: true,
      memory: true,
      structured_report: true,
      evidence_provenance: true,
      active_evidence_policy: true,
      cross_modal_clinical_decision: true,
      reader_unified_agent_bridge: true,
      audit_events: true,
    },
    llm_mode: process.env.AGENT_LLM_MODE || 'deepseek',
    server_time: new Date().toISOString(),
  });
}
