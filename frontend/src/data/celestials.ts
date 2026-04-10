export type TimelineEvent = {
  year: string;
  title: string;
  desc: string;
};

export type CelestialBody = {
  id: string;
  name: string;
  subtitle: string;
  icon: string | any;
  heroImage: string;
  gridImage: string;
  type: string;
  desc: string;
  intro: string;
  features: string[];
  exploration: string;
  timeline: TimelineEvent[];
  basicData: Record<string, string>;
  orbitData: Record<string, string>;
};

export const celestialBodies: CelestialBody[] = [
  {
    id: "sun",
    name: "太阳",
    subtitle: "Sun",
    icon: "☀",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/b/b4/The_Sun_by_the_Atmospheric_Imaging_Assembly_of_NASA%27s_Solar_Dynamics_Observatory_-_20100819.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/b/b4/The_Sun_by_the_Atmospheric_Imaging_Assembly_of_NASA%27s_Solar_Dynamics_Observatory_-_20100819.jpg",
    type: "恒星",
    desc: "太阳是太阳系的中心恒星，占太阳系总质量的99.86%。它是一颗黄矮星，为整个太阳系提供光和热。",
    intro: "太阳是太阳系的中心天体，也是离地球最近的恒星。它的引力维系着整个太阳系内所有天体的运行，其核心进行的核聚变反应释放出巨大的能量。",
    features: [
      "体积为地球的130万倍",
      "核心温度高达1500万摄氏度",
      "产生太阳风和剧烈的磁暴现象",
      "大约还有50亿年的主序星寿命"
    ],
    exploration: "人类通过帕克太阳探测器（Parker Solar Probe）和太阳动力学天文台（SDO）正在以前所未有的近距离观测太阳的日冕和磁场活动。",
    timeline: [
      { year: "1610", title: "首次望远镜观测", desc: "伽利略和哈里奥特首次通过望远镜观测到太阳黑子。" },
      { year: "1995", title: "SOHO 升空", desc: "太阳和日球层天文台发射，开始持续监测太阳内部、外层大气及太阳风。" },
      { year: "2010", title: "SDO 发射", desc: "太阳动力学天文台发射，以前所未有的高分辨率拍摄太阳。" },
      { year: "2018", title: "帕克太阳探测器", desc: "NASA发射帕克号，成为历史上最接近太阳的人造物体。" }
    ],
    basicData: {
      "类型": "主序星 (G2V)",
      "直径": "1,392,700 km",
      "质量": "1.989 × 10³⁰ kg",
      "表面温度": "约 5500 °C",
      "距地距离": "1 AU (天文单位)",
      "自转周期": "25-35 天 (赤道较快)",
      "卫星数": "八大行星与无数小天体"
    },
    orbitData: {
      "银河系公转半径": "约2.6万光年",
      "公转周期": "约2.25至2.5亿年",
      "所属星系": "银河系猎户臂"
    }
  },
  {
    id: "mercury",
    name: "水星",
    subtitle: "Mercury",
    icon: "☿",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/4/4a/Mercury_in_true_color.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/4/4a/Mercury_in_true_color.jpg",
    type: "行星",
    desc: "水星是太阳系中最小的行星，也是距离太阳最近的行星。表面布满环形山，类似月球。",
    intro: "水星由于最靠近太阳，受太阳引力影响极大。它几乎没有大气，因此拥有极大的昼夜温差，表面布满了远古陨石撞击坑。",
    features: [
      "强烈的昼夜温差 (-180°C 到 430°C)",
      "太阳系中最小的行星，并且正在缓慢缩小",
      "没有天然卫星和光环",
      "核心非常大，含铁比例极高"
    ],
    exploration: "信使号（MESSENGER）探测器曾对水星进行了详细的轨道测绘。目前，欧空局和日本联合研发的贝皮可伦坡号（BepiColombo）正在前往水星的途中。",
    timeline: [
      { year: "1974", title: "水手10号", desc: "首次飞越水星，传回了其表面的第一批近距离照片。" },
      { year: "2004", title: "信使号发射", desc: "NASA发射信使号探测器，成为首个环绕水星运行的航天器。" },
      { year: "2011", title: "进入水星轨道", desc: "信使号成功进入轨道，开始了为期四年的详细科学测绘。" },
      { year: "2018", title: "贝皮可伦坡号", desc: "欧空局和日空局联合发射探测器，预计2025年抵达。" }
    ],
    basicData: {
      "类型": "类地行星",
      "直径": "4,879 km",
      "质量": "3.30 × 10²³ kg",
      "表面温度": "-180°C 到 430°C",
      "距太阳": "0.39 AU",
      "公转周期": "88 天",
      "自转周期": "58.6 天",
      "卫星数": "0"
    },
    orbitData: {
      "轨道偏心率": "0.205",
      "轨道倾角": "7.00°"
    }
  },
  {
    id: "venus",
    name: "金星",
    subtitle: "Venus",
    icon: "♀",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/e/e5/Venus-real_color.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/e/e5/Venus-real_color.jpg",
    type: "行星",
    desc: "金星是太阳系中最热的行星，拥有浓厚的大气层，主要由二氧化碳组成，产生强烈的温室效应。",
    intro: "金星常被称为地球的“姐妹星”，因为两者在大小和质量上极其相似。但金星有着十分恶劣的环境，不仅被厚厚的硫酸云笼罩，其表面还呈现极端的高温和高压。",
    features: [
      "太阳系最热的行星，地表超过 460°C",
      "极端的温室效应导致高温",
      "逆向自转（太阳从西边升起）",
      "大气压强达到地球的92倍"
    ],
    exploration: "前苏联的麦哲伦号（Magellan）和金星计划（Venera）曾成功着陆并传回数据。未来NASA与ESA计划发射多艘探测器（如VERITAS和EnVision）重返金星。",
    timeline: [
      { year: "1962", title: "水手2号", desc: "人类首个成功飞越另一颗行星的探测器，确认了金星的高温环境。" },
      { year: "1970", title: "金星7号", desc: "苏联探测器首次在金星表面软着陆，并传回了23分钟的数据。" },
      { year: "1990", title: "麦哲伦号", desc: "利用雷达技术绘制了金星98%表面的地形图。" },
      { year: "2005", title: "金星快车", desc: "欧空局首个金星探测器，对大气进行了长期深入研究。" }
    ],
    basicData: {
      "类型": "类地行星",
      "直径": "12,104 km",
      "质量": "4.86 × 10²⁴ kg",
      "表面温度": "平均约 462°C",
      "距太阳": "0.72 AU",
      "公转周期": "225 天",
      "自转周期": "-243 天 (逆行)",
      "卫星数": "0"
    },
    orbitData: {
      "轨道偏心率": "0.0068 (近乎正圆)",
      "轨道倾角": "3.39°"
    }
  },
  {
    id: "earth",
    name: "地球",
    subtitle: "Earth",
    icon: "⊕",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/9/97/The_Earth_seen_from_Apollo_17.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/9/97/The_Earth_seen_from_Apollo_17.jpg",
    type: "行星",
    desc: "地球是我们的家园，是目前已知唯一存在生命的行星。拥有液态水、适宜的大气和磁场保护。",
    intro: "地球是我们居住的蓝色星球，由于表面约71%被水循环系统覆盖，且处于宜居带中，地球孕育了庞大且复杂的生命网络。",
    features: [
      "目前全宇宙已知唯一存在生命的天体",
      "表面大部分被液态水覆盖",
      "拥有富含氧气和氮气的大气层",
      "活跃的板块运动和强大的地磁场"
    ],
    exploration: "人类不仅在地球轨道上建立了国际空间站与大量观测卫星网络，还在持续开展深海探索与对地球地表变迁的气候监测。",
    timeline: [
      { year: "1957", title: "斯普特尼克1号", desc: "人类首颗人造卫星发射，开启了航天时代。" },
      { year: "1961", title: "加加林进入太空", desc: "苏联宇航员尤里·加加林成为首个进入地球轨道的登山。" },
      { year: "1998", title: "国际空间站动工", desc: "多国合作建立的长期近地轨道实验平台开始组装。" },
      { year: "2015", title: "DSCOVR 观测", desc: "深空气候观测台提供全天候的地球正面实时高清影像。" }
    ],
    basicData: {
      "类型": "类地行星",
      "直径": "12,742 km",
      "质量": "5.97 × 10²⁴ kg",
      "表面温度": "平均约 15°C",
      "距太阳": "1.00 AU",
      "公转周期": "365.25 天",
      "自转周期": "23小时56分",
      "卫星数": "1 (月球)"
    },
    orbitData: {
      "轨道偏心率": "0.0167",
      "轨道倾角": "0.00° (以此为参考基准)"
    }
  },
  {
    id: "moon",
    name: "月球",
    subtitle: "Moon",
    icon: "☾",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/e/e1/FullMoon2010.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/e/e1/FullMoon2010.jpg",
    type: "卫星",
    desc: "月球是地球唯一的天然卫星。几十年来一直是人类深空探测和登陆外星的首站。",
    intro: "月球是离地球最近的自然天体。它不仅通过引力引发地球上的潮汐，稳定地球的自转轴，其表面还保留了数十亿年来的陨石撞击坑，是一本宇宙的历史书。",
    features: [
      "被地球潮汐锁定，永远以同一面朝向地球",
      "质量约为地球的 1/81，引力为 1/6",
      "缺乏大气层，昼夜温差极大",
      "表面分为明亮的高地和黑暗的月海"
    ],
    exploration: "阿波罗计划实现了人类的首次登月。现在全球正通过阿尔忒弥斯计划（Artemis）和嫦娥工程进行月球基地的建设准备和背面取样返回。",
    timeline: [
      { year: "1959", title: "月球2号", desc: "首个人造物体到达月球表面（硬着陆）。" },
      { year: "1969", title: "阿波罗11号", desc: "阿姆斯特朗成为首个踏上月球的人类，“个人一小步，人类一大步”。" },
      { year: "2019", title: "嫦娥四号", desc: "中国探测器首次实现人类航天器在月球背面软着陆。" },
      { year: "2024", title: "阿尔忒弥斯计划", desc: "NASA启动重返月球计划，旨在建立长期月球科研基地。" }
    ],
    basicData: {
      "类型": "卫星",
      "直径": "3,474 km",
      "质量": "7.34 × 10²² kg",
      "表面温度": "夜间-173°C 到 白天117°C",
      "距地球": "平均 384,400 km",
      "公转周期": "27.3 天",
      "自转周期": "27.3 天 (同步自转)",
      "卫星数": "0"
    },
    orbitData: {
      "轨道偏心率": "0.0549",
      "轨道倾角": "5.14° (相对于黄道面)"
    }
  },
  {
    id: "mars",
    name: "火星",
    subtitle: "Mars",
    icon: "♂",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/0/02/OSIRIS_Mars_true_color.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/0/02/OSIRIS_Mars_true_color.jpg",
    type: "行星",
    desc: "火星被称为红色星球，表面富含氧化铁。拥有太阳系最高的山峰奥林帕斯山和最大的峡谷。",
    intro: "火星是一颗寒冷、长满铁锈色沙尘的荒凉沙漠行星。其极其稀薄的大气和远古水流侵蚀过的地形让人类科学家相信，火星可能曾有适合微小生命存在的自然环境。",
    features: [
      "地表的超量氧化铁赋予了其红色的外观",
      "太阳系最高的山峰：奥林帕斯山 (Olympus Mons)",
      "长达数千公里的水手号大峡谷",
      "两极分布有水冰和干冰构成的巨大极冠"
    ],
    exploration: "好奇号、毅力号和祝融号等火星车正在地表穿梭探测。大量轨道上的探测器不断描绘其地质变迁，为未来的载人火星任务铺路。",
    timeline: [
      { year: "1965", title: "水手4号", desc: "获得人类历史上首张从深空拍摄到的另一颗行星的照片。" },
      { year: "1976", title: "海盗1号", desc: "美国探测器首次成功在火星表面软着陆，持续工作6年。" },
      { year: "2012", title: "好奇号登陆", desc: "大型核动力火星车着陆，开始寻找过去可能存在生命的证据。" },
      { year: "2021", title: "毅力号与祝融号", desc: "美中两国的火星车相继成功着陆，开启火星探测新纪元。" }
    ],
    basicData: {
      "类型": "类地行星",
      "直径": "6,779 km",
      "质量": "6.42 × 10²³ kg",
      "表面温度": "平均约 -63°C",
      "距太阳": "1.52 AU",
      "公转周期": "687 天",
      "自转周期": "24小时37分",
      "卫星数": "2 (火卫一、火卫二)"
    },
    orbitData: {
      "轨道偏心率": "0.0934",
      "轨道倾角": "1.85°"
    }
  },
  {
    id: "jupiter",
    name: "木星",
    subtitle: "Jupiter",
    icon: "♃",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/e/e2/Jupiter.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/e/e2/Jupiter.jpg",
    type: "行星",
    desc: "木星是太阳系最大的行星，质量是其他所有行星总和的2.5倍。著名的大红斑是持续数百年的风暴。",
    intro: "木星是一颗巨大的气态巨行星。它的巨大引力保护了内太阳系免受过多的小行星和彗星撞击，它还拥有一个类似于微型太阳系的庞大卫星系统。",
    features: [
      "总质量是所有其他已知行星总和的 2.5 倍",
      "最具视觉特征的大红斑（比地球还大的反气旋）",
      "自身能散发出比接收到的太阳光更多的热量",
      "拥有极强且致密的磁场和辐射带"
    ],
    exploration: "旅行者号飞车掠过了它，伽利略号和朱诺号（Juno）对其大气和磁场进行了极高质量的探测，接下来的木卫二快船（Europa Clipper）将专门探索其可能宜居的卫星。",
    timeline: [
      { year: "1973", title: "先驱者10号", desc: "首个穿越小行星带并近距离飞越木星的航天器。" },
      { year: "1979", title: "旅行者1号/2号", desc: "发现木星的光环以及木卫一上的活火山活动。" },
      { year: "1995", title: "伽利略号环绕", desc: "首个长期环绕木星的探测器，并向木星大气层释放了探测器。" },
      { year: "2016", title: "朱诺号抵达", desc: "开始对木星内部结构、大气成分和磁场进行高精度测量。" }
    ],
    basicData: {
      "类型": "气态巨行星",
      "直径": "139,820 km",
      "质量": "1.898 × 10²⁷ kg",
      "云层温度": "约 -145 °C",
      "距太阳": "5.20 AU",
      "公转周期": "11.86 年",
      "自转周期": "9.9 小时",
      "卫星数": "95"
    },
    orbitData: {
      "轨道偏心率": "0.0489",
      "轨道倾角": "1.31°"
    }
  },
  {
    id: "saturn",
    name: "土星",
    subtitle: "Saturn",
    icon: "♄",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/c/c7/Saturn_during_Equinox.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/c/c7/Saturn_during_Equinox.jpg",
    type: "行星",
    desc: "土星以其壮观的环系统闻名，环主要由冰和岩石组成。它的密度比水还小。",
    intro: "土星是太阳系内的一颗“皇冠明珠”。那极其复杂的环带系统其实是由无数碎冰块、尘埃和岩石组成，而在其静谧外观的背后隐藏着狂暴的超高速赤道风带。",
    features: [
      "拥有太阳系中最宏大与最易观测的星环系统",
      "太阳系中唯一整体密度比水还要小的行星",
      "北极存在着神秘的持久性六边形风暴",
      "其最大的卫星土卫六（泰坦）拥有浓厚大气"
    ],
    exploration: "传奇的卡西尼-惠更斯计划极其深入地研究了土星、光环和卫星。人类甚至让惠更斯号成功穿越了土卫六的大气层并降落在其地表上。",
    timeline: [
      { year: "1979", title: "先驱者11号", desc: "首次近距离探测土星，发现了新的光环和卫星。" },
      { year: "1980", title: "旅行者1号", desc: "传回了土星光环及卫星泰坦（土卫六）的高清图像。" },
      { year: "2004", title: "卡西尼号入轨", desc: "美欧合作的宏伟计划，对土星系统进行了长达13年的详细探索。" },
      { year: "2017", title: "大结局任务", desc: "卡西尼号在此期间多次穿越土星环，最终主动坠入土星大气。" }
    ],
    basicData: {
      "类型": "气态巨行星",
      "直径": "116,460 km",
      "质量": "5.68 × 10²⁶ kg",
      "云层温度": "约 -178 °C",
      "距太阳": "9.58 AU",
      "公转周期": "29.45 年",
      "自转周期": "10.7 小时",
      "卫星数": "146"
    },
    orbitData: {
      "轨道偏心率": "0.0565",
      "轨道倾角": "2.48°"
    }
  },
  {
    id: "uranus",
    name: "天王星",
    subtitle: "Uranus",
    icon: "♅",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/3/3d/Uranus2.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/3/3d/Uranus2.jpg",
    type: "行星",
    desc: "天王星是一颗冰巨星，拥有独特的躺着自转的方式，自转轴几乎平行于黄道面。",
    intro: "由于其独特的高自转轴倾角（接近成90度横躺在轨道上），天王星经历了极端且漫长的极地季节。它的大气以甲烷为主，吸收了红光赋予其美丽的淡蓝色调。",
    features: [
      "躺着自转，导致单侧极地经历长达42年的白昼",
      "拥有太阳系内极其寒冷的行星大气",
      "深层核心由大量的水、氨和甲烷组成的流体“冰”构成",
      "错综复杂的幽暗光环和多颗微小的卫星群"
    ],
    exploration: "目前人类仅有旅行者2号在1986年近距离飞越过天王星。多个空间机构目前正在认真评估于未来几十年内发射轨道探测器前往该体系的任务。",
    timeline: [
      { year: "1781", title: "赫歇尔发现", desc: "威廉·赫歇尔首次通过望远镜发现天王星，确认其为行星。" },
      { year: "1977", title: "发现星环", desc: "天文学家在观测掩星现象时意外发现了天王星的暗淡星环。" },
      { year: "1986", title: "旅行者2号飞越", desc: "人类历史上唯一一次对天王星的近距离探访，传回大量宝贵资料。" },
      { year: "2020", title: "JWST 观测", desc: "詹姆斯·韦伯空间望远镜拍摄到天王星极具动态的星环细节。" }
    ],
    basicData: {
      "类型": "冰巨行星",
      "直径": "50,724 km",
      "质量": "8.68 × 10²⁵ kg",
      "表面温度": "约 -224 °C",
      "距太阳": "19.2 AU",
      "公转周期": "84 年",
      "自转周期": "-17.2 小时 (逆行)",
      "卫星数": "28"
    },
    orbitData: {
      "轨道偏心率": "0.0463",
      "轨道倾角": "0.77°"
    }
  },
  {
    id: "neptune",
    name: "海王星",
    subtitle: "Neptune",
    icon: "♆",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/5/56/Neptune_Full.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/5/56/Neptune_Full.jpg",
    type: "行星",
    desc: "海王星是太阳系最远的大行星。其表面颜色深蓝，并且存在太阳系级别最疯狂的风暴。",
    intro: "海王星作为太阳系内离太阳最远的八大行星。在深邃幽蓝的大气表面下，海王星内部隐藏着极其激烈的气象运动，产生了太阳系最为恐怖的超音速风暴。",
    features: [
      "太阳系风速最快的行星（风暴最高速度超 2100 km/h）",
      "深蓝色调不仅源于甲烷，还可能包含微量的未知化合物",
      "拥有五条极其微弱且物质不均匀的暗弱光环系统",
      "最大暗斑和罕见的活跃逆行卫星（海卫一 Triton）"
    ],
    exploration: "旅行者2号在1989年完成了对它的惊险飞掠并发现巨大黑斑。哈勃和JWST望远镜现正接力遥测，观察其大气的风暴系统变化。",
    timeline: [
      { year: "1846", title: "数学预言与发现", desc: "通过数学计算预测其位置后，伽勒在柏林天文台首次观测到它。" },
      { year: "1989", title: "旅行者2号飞越", desc: "人类首次近距离观测，发现了“大黑斑”及海卫一上的冰火山。" },
      { year: "2011", title: "完成一圈公转", desc: "自1846年被发现后，海王星完成了其轨道上的首个完整“年”。" },
      { year: "2022", title: "JWST 高清星环", desc: "韦伯望远镜以前所未有的清晰度展示了海王星微弱的尘埃环。" }
    ],
    basicData: {
      "类型": "冰巨行星",
      "直径": "49,244 km",
      "质量": "1.02 × 10²⁶ kg",
      "表面温度": "约 -214°C",
      "距太阳": "30.1 AU",
      "公转周期": "164.8 年",
      "自转周期": "16.1 小时",
      "卫星数": "16"
    },
    orbitData: {
      "轨道偏心率": "0.0086",
      "轨道倾角": "1.77°"
    }
  },
  {
    id: "pluto",
    name: "冥王星",
    subtitle: "Pluto",
    icon: "♇",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/e/ef/Pluto_in_True_Color_-_High-Res.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/e/ef/Pluto_in_True_Color_-_High-Res.jpg",
    type: "矮行星",
    desc: "冥王星是太阳系外侧的著名矮行星。其拥有一颗巨大的伴星冥卫一，并在表面烙印着巨大的白色心形区域。",
    intro: "冥王星长期以来被视为太阳系第九大行星，直到被重新归类。表面分布着广阔的固态氮冰川以及大量的水冰山脉，位于边缘的柯伊伯带。",
    features: [
      "由于其较小体积与共轨特征被归类为矮行星",
      "表面带有鲜明的心形区域“汤博区” (Tombaugh Regio)",
      "与其卫星冥卫一组成极度罕见的双星系统状态",
      "公转轨道非常椭圆并会倾斜穿越海王星轨道"
    ],
    exploration: "2015年新视野号 (New Horizons) 航天器历史性地飞越冥王星，向地球传回了惊艳无比的高清彩色图像。",
    timeline: [
      { year: "1930", title: "汤博发现", desc: "克莱德·汤博在洛威尔天文台发现了这颗偏远的星球。" },
      { year: "2006", title: "降级为矮行星", desc: "国际天文学联合会重新定义行星，冥王星被重新归类。" },
      { year: "2006", title: "新视野号发射", desc: "NASA发射了人类历史上速度最快的探测器前往冥王星。" },
      { year: "2015", title: "历史性飞越", desc: "新视野号首次近距离飞越冥王星，发现表面巨大的“心脏”冰原。" }
    ],
    basicData: {
      "类型": "矮行星",
      "直径": "2,376 km",
      "质量": "1.30 × 10²² kg",
      "表面温度": "约 -229 °C",
      "距太阳": "平均 39.5 AU",
      "公转周期": "248 年",
      "自转周期": "-6.38 天 (逆行)",
      "卫星数": "5"
    },
    orbitData: {
      "轨道偏心率": "0.2488",
      "轨道倾角": "17.16°"
    }
  },
  {
    id: "ceres",
    name: "谷神星",
    subtitle: "Ceres",
    icon: "⚳",
    gridImage: "https://upload.wikimedia.org/wikipedia/commons/7/76/Ceres_-_RC3_-_Haulani_Crater_%2822381131691%29_%28cropped%29.jpg",
    heroImage: "https://upload.wikimedia.org/wikipedia/commons/7/76/Ceres_-_RC3_-_Haulani_Crater_%2822381131691%29_%28cropped%29.jpg",
    type: "矮行星",
    desc: "谷神星是小行星带中最大的天体，也是唯一的矮行星。被认为是保存有早期内部水的原始天体。",
    intro: "谷神星位于火星和木星之间的小行星带，是该区域内唯一通过自身重力达到静力平衡（呈球形）的天体。它不仅含有大量的冰水物质，还被认为是太阳系演化早期的重要时间胶囊。",
    features: [
      "小行星带中体积最大、引力最大的单一星体",
      "地壳之下可能存在着广阔的冰冻层甚至液态大洋",
      "表面存在几处极其明亮的神秘反光盐斑（如奥卡托撞击坑）",
      "是一颗仍在演化的类地天体过渡形态"
    ],
    exploration: "NASA的黎明号（Dawn）探测器在2015年成功进入了谷神星轨道，不仅传回了前所未见的地表高清图，更成为人类首个深入环绕矮行星探测的航天英雄。",
    timeline: [
      { year: "1801", title: "皮亚齐发现", desc: "朱塞普·皮亚齐发现了它，最初被认为是一颗缺失的行星。" },
      { year: "2007", title: "黎明号发射", desc: "NASA发射探测器，旨在研究小行星带中两颗最大的天体。" },
      { year: "2015", title: "进入轨道", desc: "黎明号抵达谷神星，成为首个环绕矮行星运行的航天器。" },
      { year: "2018", title: "任务结束", desc: "黎明号耗尽燃料，保持在谷神星轨道上成为永久的“纪念碑”。" }
    ],
    basicData: {
      "类型": "矮行星",
      "直径": "939 km",
      "质量": "9.39 × 10²⁰ kg",
      "表面温度": "约 -105 °C",
      "距太阳": "2.77 AU",
      "公转周期": "4.6 年",
      "自转周期": "9.1 小时",
      "卫星数": "0"
    },
    orbitData: {
      "轨道偏心率": "0.0758",
      "轨道倾角": "10.59°"
    }
  }
];
