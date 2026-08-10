# Offline Autoresearch Loop Summary

- Generated: `2026-08-10T05:06:56Z`
- Dry-run: `True`
- Trials in history: 5
- Best trial: `AR_20260810_005` val_macro_auc=0.635
- Code hash: `055cf2bbf1db2c41`

## Reflection

- best_trial=AR_20260810_005 val_macro_auc=0.635
- prefer_modules=['M1_convnext_logits', 'M2_dino_nca', 'M3_wall_border_delta', 'M5_clinical22']
- avoid_or_revisit=['M1_convnext_logits', 'M2_dino_nca', 'M5_clinical22'] (worst=0.628)
- do not use external labels for selection
- clinical Agent path must remain frozen-weight

## Guardrails

- Offline only; never writes clinical Agent active memory
- Never mutates frozen mainline checkpoint directories
- Val for selection only; external/prospective are final audit
- Budget: <=30 trials, <=2 epochs/trial