import { Patient } from '@/types';

function cohortKey(patient: Patient): string {
  return `${patient.patient_id}|${patient.group}|${patient.source_label}`;
}

/**
 * 队列统计应按「患者×治疗组」去重，不能按每一帧图像重复计数。
 * 优先保留带标注的帧作为代表。
 */
export function dedupePatientsForStatistics(patients: Patient[]): Patient[] {
  const bestByKey = new Map<string, Patient>();

  for (const patient of patients) {
    const key = cohortKey(patient);
    const existing = bestByKey.get(key);
    if (!existing) {
      bestByKey.set(key, patient);
      continue;
    }

    const existingScore =
      (existing.segmentation?.has_annotation ? 4 : 0) +
      (existing.segmentation?.has_overlay ? 2 : 0) +
      (existing.clinical ? 1 : 0);
    const candidateScore =
      (patient.segmentation?.has_annotation ? 4 : 0) +
      (patient.segmentation?.has_overlay ? 2 : 0) +
      (patient.clinical ? 1 : 0);

    if (candidateScore > existingScore) {
      bestByKey.set(key, patient);
    }
  }

  return Array.from(bestByKey.values());
}
