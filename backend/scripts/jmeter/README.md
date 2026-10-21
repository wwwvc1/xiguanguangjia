# JMeter 压测使用说明

## 1. 准备测试账号(已写好脚本)

```powershell
cd "C:\Users\wangchang\Desktop\脚本练习\个人习惯小程序\backend"
.\.venv\Scripts\Activate.ps1
python -m scripts.jmeter.setup_data
```

会生成 `scripts/jmeter/auth.json`,里面有:
- `base_url`: `http://127.0.0.1:8000`
- `token`: 已登录的 token
- `username` / `password`

## 2. JMeter 准备

### 方案 A:用 GUI(初学者推荐)

1. 启动 JMeter:`C:\apache-jmeter-5.6.3\bin\jmeter.bat`
2. **测试计划 → 添加 → 线程(用户)**:
   - 线程数:50
   - Ramp-up:10 秒
   - 循环次数:100(或勾"永远")
3. **线程组 → 添加 → 取样器 → HTTP 请求**:
   - 协议:HTTP
   - 域名:`127.0.0.1`
   - 端口:`8000`
   - 方法:GET
   - 路径:`/api/transactions/?year=2026&month=9`
4. **HTTP 请求 → 添加 → 配置元件 → HTTP 信息头管理器**:
   - 添加: `Authorization` = `Bearer ${__P(token)}`
5. **测试计划 → 添加 → 配置元件 → 用户定义的变量**:
   - 添加: `token` = `eyJ...`(从 auth.json 复制)
6. **线程组 → 添加 → 监听器 → 聚合报告**(看结果)
7. **Ctrl+S** 保存为 `scripts/jmeter/plan.jmx`

### 方案 B:命令行(适合 CI/批量)

我帮你写好了一个现成的测试计划 `plan.jmx`,直接用:

```cmd
cd C:\apache-jmeter-5.6.3\bin
jmeter -n -t "C:\path\to\plan.jmx" -l result.jtl -e -o report
```

## 3. 看报告

GUI 跑完会直接出图。命令行跑完打开 `report/index.html` 看 HTML 报告。

关键指标:
- **Throughput**(吞吐量):每秒处理请求数
- **Response Time**(响应时间):平均 / P95 / P99
- **Error %**(错误率):应 < 1%
