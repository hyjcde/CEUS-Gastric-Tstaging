export type Language = 'en' | 'zh';

export const dictionary = {
  en: {
    title: 'Gastric Cancer T-Staging AI',
    subtitle: 'Research Workstation',
    hospital: 'FUJIAN XIEHE ULTRASOUND',
    dept: 'Dept.US',
    protocol: 'GC_Protocol',
    live: 'LIVE_SESSION',
    status: {
        online: 'PACS: CONNECTED',
        model: 'Model: Research Prototype',
        gpu: 'GPU ACCEL'
    },
    userMenu: {
        name: 'Dr. Lin',
        role: 'Chief Physician',
        profile: 'Profile',
        reports: 'My Reports',
        settings: 'System Settings',
        signout: 'Sign Out'
    },
    cohort: {
        title: 'Study Cohort',
        search: 'Filter by PID / MRN...',
        loading: 'Loading Cohort...',
        total: 'TOTAL'
    },
    viewer: {
        noData: 'No Imaging Data Loaded',
        source: 'Source',
        cropUi: 'CROP UI',
        originalView: 'ORIGINAL',
        seg: 'Seg',
        xai: 'XAI',
        contrast: 'Contrast',
        ruler: 'Ruler',
        bmode: 'B-MODE',
        mask: 'AI SEGMENTATION',
        heatmap: 'GRAD-CAM ATTENTION MAP',
        detect: 'Detection',
        detection_box: 'Detection ROI',
        detection_missing: 'ROI not available'
    },
    reasoning: {
        title: 'Pathology Features (CBM)',
        interactive: 'Interactive',
        sliders: {
            c1: 'Serosa Continuity',
            c2: 'Wall Stiffness',
            c3: 'Doppler Flow',
            c4: 'Lymph Node Axis',
            labels: {
                c1: ['Intact', 'Disrupted'],
                c2: ['Soft (Normal)', 'Hard (Fibrosis)'],
                c3: ['Hypovascular', 'Hypervascular'],
                c4: ['S/L < 0.5', 'S/L > 0.5']
            }
        }
    },
    diagnosis: {
        title: 'Diagnosis',
        predicted: 'Predicted Stage',
        confidence: 'Model Confidence',
        risk_high: 'HIGH RISK',
        risk_low: 'LOW RISK',
        serosa_invaded: 'Serosa Invaded',
        localized: 'Subserosa/Muscularis',
        invasion_detected: 'SEROSA INVASION DETECTED',
        localized_disease: 'LOCALIZED DISEASE',
        report_header: 'Automated Report',
        waiting: 'Waiting for input...',
        clinical: 'Clinical Data',
        no_clinical: 'No Clinical Data Available',
        demographics: 'Demographics',
        tumor_size: 'Tumor Size',
        biomarkers: 'Biomarkers',
        case_summary: 'Case Summary',
        segmentation_assets: 'Segmentation Assets',
        agent_readiness: 'Agent Draft',
        pathology: 'Pathology',
        ground_truth: 'Ground Truth (Post-Op)',
        ai_vs_gt: 'AI vs Ground Truth',
        ai_prediction: 'AI Prediction',
        post_op_pathology: 'Post-Op Pathology',
        prediction_matched: 'Prediction Matched',
        available_data: 'Available Data',
        imaging_only: 'Imaging analysis and AI prediction only'
    }
  },
  zh: {
    title: '胃癌T分期智能辅助系统',
    subtitle: '科研工作站',
    hospital: '福建协和医院超声科',
    dept: '超声科',
    protocol: '胃癌分期协议',
    live: '实时会诊',
    status: {
        online: 'PACS: 已连接',
        model: '模型: 研究型模型',
        gpu: 'GPU 加速中'
    },
    userMenu: {
        name: '林医生',
        role: '主任医师',
        profile: '个人资料',
        reports: '我的报告',
        settings: '系统设置',
        signout: '退出登录'
    },
    cohort: {
        title: '研究队列',
        search: '搜索 PID / 病历号...',
        loading: '加载队列中...',
        total: '总计'
    },
    viewer: {
        noData: '未加载影像数据',
        source: '主视图',
        cropUi: 'CROP UI',
        originalView: '原图',
        seg: '分割',
        xai: '热力图',
        contrast: '对比',
        ruler: '标尺',
        bmode: '二维超声 (B-Mode)',
        mask: 'AI 分割掩膜',
        heatmap: 'Grad-CAM 注意力图',
        detect: '检测',
        detection_box: '检测 ROI',
        detection_missing: 'ROI 数据缺失'
    },
    reasoning: {
        title: '病理特征推理 (CBM)',
        interactive: '交互模式',
        sliders: {
            c1: '浆膜层连续性',
            c2: '胃壁硬度 (弹性)',
            c3: '多普勒血流',
            c4: '淋巴结长短径比',
            labels: {
                c1: ['连续完整', '明显中断'],
                c2: ['软 (正常)', '硬 (纤维化)'],
                c3: ['乏血供', '富血供'],
                c4: ['S/L < 0.5', 'S/L > 0.5']
            }
        }
    },
    diagnosis: {
        title: '智能诊断',
        predicted: '预测分期',
        confidence: '置信度',
        risk_high: '高风险',
        risk_low: '低风险',
        serosa_invaded: '浆膜受侵',
        localized: '局限于肌层/浆膜下',
        invasion_detected: '检测到浆膜侵犯',
        localized_disease: '局限性病变',
        report_header: 'AI 自动生成报告',
        waiting: '等待输入...',
        clinical: '临床数据',
        no_clinical: '无临床数据',
        demographics: '基本信息',
        tumor_size: '肿瘤大小',
        biomarkers: '肿瘤标志物',
        case_summary: '病例摘要',
        segmentation_assets: '分割资产',
        agent_readiness: 'Agent 草稿',
        pathology: '病理信息',
        ground_truth: '术后病理 (金标准)',
        ai_vs_gt: 'AI预测 vs 金标准',
        ai_prediction: 'AI预测',
        post_op_pathology: '术后病理',
        prediction_matched: '预测匹配',
        available_data: '可用数据',
        imaging_only: '仅影像分析和AI预测'
    }
  }
};
