import React, {useEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import Hls from 'hls.js';
import {AreaChart,Area,LineChart,Line,CartesianGrid,XAxis,YAxis,Tooltip,ResponsiveContainer,BarChart,Bar} from 'recharts';
import {Activity,BrainCircuit,Network,Database,Cloud,Play,Pause,RefreshCw,Wifi,AlertTriangle,Video,Server,Clock3} from 'lucide-react';
import './style.css';
const API = import.meta.env.VITE_API_BASE || '';
const fmt = (v,d=1)=>Number(v||0).toLocaleString(undefined,{maximumFractionDigits:d});
function App(){
 const [health,setHealth]=useState(null),[summary,setSummary]=useState(null),[forecast,setForecast]=useState(null),[graph,setGraph]=useState(null),[metrics,setMetrics]=useState([]);
 const [events,setEvents]=useState([]),[connected,setConnected]=useState(false),[playing,setPlaying]=useState(false),[speed,setSpeed]=useState('3'),[hlsUrl,setHlsUrl]=useState('/videos/sample.mp4'),[videoStatus,setVideoStatus]=useState('Paste a browser-accessible HLS URL and press Load stream.'),[latency,setLatency]=useState(null);
 const wsRef=useRef(null),videoRef=useRef(null),hlsRef=useRef(null),lastEvents=useRef([]);
 const refresh=async()=>{try{const [h,s,f,g,m]=await Promise.all(['/api/health','/api/summary','/api/forecast','/api/graph','/api/metrics'].map(p=>fetch(API+p).then(r=>r.json())));setHealth(h);setSummary(s);setForecast(f);setGraph(g);setMetrics(m.measurements||[])}catch(e){setHealth({status:'unreachable',error:String(e)})}};
 useEffect(()=>{refresh();const t=setInterval(refresh,5000);return()=>clearInterval(t)},[]);
 const connect=()=>{if(wsRef.current){wsRef.current.close();wsRef.current=null;setPlaying(false);return} const proto=location.protocol==='https:'?'wss':'ws';const base=API?new URL(API,location.href):location;const url=`${proto}://${base.host}/ws/live?speed=${speed}`;const ws=new WebSocket(url);wsRef.current=ws;ws.onopen=()=>{setConnected(true);setPlaying(true)};ws.onmessage=e=>{let m;try{m=JSON.parse(e.data)}catch{return}if(m.type==='historical_replay'){setEvents(prev=>{const next=[...prev,{time:m.record.startedDateTime,latency:m.record.time_ms||0,bytes:m.record.content_size||0,status:m.record.status||0,host:m.record.hostname||'unknown',asset:m.record.asset_type||'other',index:m.index}].slice(-80);lastEvents.current=next;return next})}};ws.onclose=()=>{setConnected(false);setPlaying(false);wsRef.current=null};ws.onerror=()=>setConnected(false)};
 useEffect(()=>()=>{wsRef.current?.close();hlsRef.current?.destroy()},[]);
 
const loadVideo = () => {
  const v = videoRef.current;
  if (!v || !hlsUrl.trim()) return;

  hlsRef.current?.destroy();
  hlsRef.current = null;

  const url = hlsUrl.trim();
  v.pause();
  v.removeAttribute('src');
  v.load();

  if (url.toLowerCase().split('?')[0].endsWith('.mp4')) {
    v.src = url;
    v.load();
    setVideoStatus('MP4 loaded. Press Play to start.');
    return;
  }

  setVideoStatus('Loading HLS manifest…');

  if (Hls.isSupported()) {
    const hls = new Hls();
    hlsRef.current = hls;
    hls.loadSource(url);
    hls.attachMedia(v);

    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      setVideoStatus('HLS manifest loaded. Press Play to start.');
    });

    hls.on(Hls.Events.ERROR, (_, data) => {
      if (data.fatal) {
        setVideoStatus(`HLS error: ${data.details}`);
      }
    });
  } else if (v.canPlayType('application/vnd.apple.mpegurl')) {
    v.src = url;
    v.load();
    setVideoStatus('Native HLS playback selected.');
  } else {
    setVideoStatus('This browser does not support HLS playback.');
  }
};
 const measureLatency=async()=>{const t=performance.now();try{const r=await fetch(API+'/api/health',{cache:'no-store'});await r.json();setLatency({ms:(performance.now()-t).toFixed(2),kind:'browser-to-deployed-API round trip',at:new Date().toLocaleTimeString()})}catch(e){setLatency({ms:'—',kind:'Request failed: '+String(e)})}};
 const chart=useMemo(()=>events.slice(-40).map((e,i)=>({i:i+1,latency:Number(e.latency)||0,KB:(Number(e.bytes)||0)/1024,requests:1})),[events]);
 const hostBars=useMemo(()=>Object.entries(events.reduce((a,e)=>(a[e.host]=(a[e.host]||0)+1,a),{})).map(([hostname,requests])=>({hostname,requests})),[events]);
 return <div className="app"><header className="topbar"><div className="brand"><div className="brand-icon"><Activity/></div><div><strong>EDGE<span>CAST</span></strong><small>CDN BANDWIDTH OPTIMIZER</small></div></div><div className="top-right"><span className={`pill ${health?.status==='ok'?'ok':'bad'}`}><i/> {health?.status==='ok'?'API CONNECTED':'API OFFLINE'}</span><span className="pill subtle"><Database size={14}/> Bandwidth.csv · {summary?.rows||'…'} records</span></div></header>
 <main><section className="hero"><div><div className="eyebrow"><span className="live-dot"/> REAL-DATA TRACE ANALYTICS</div><h1>Predict demand.<br/><em>Optimize delivery.</em></h1><p>Explore recorded CDN requests, trained LSTM forecasts, hostname graph inference, and measured latency from this deployed app.</p><div className="hero-actions"><button className="primary" onClick={connect}>{connected?<Pause size={16}/>:<Play size={16}/>} {connected?'Stop trace replay':'Start trace replay'}</button><label className="speed">Replay speed <select value={speed} onChange={e=>setSpeed(e.target.value)}><option value="1">1×</option><option value="3">3×</option><option value="8">8×</option><option value="20">20×</option></select></label></div><div className="notice"><AlertTriangle size={15}/> Historical trace replay is not live Internet traffic. Live API timing is measured separately.</div></div><div className="hero-graphic"><div className="orb orb1"/><div className="orb orb2"/><div className="network-core"><Network size={48}/><b>EDGE<br/>NETWORK</b></div><div className="node n1">LSTM</div><div className="node n2">GNN</div><div className="node n3">CACHE</div><div className="connect-line l1"/><div className="connect-line l2"/><div className="connect-line l3"/></div></section>
 <section className="metrics-grid"><Metric icon={<Activity/>} label="Observed requests" value={summary?.rows??'—'} sub="Rows in supplied CSV"/><Metric icon={<Clock3/>} label="Observed p95 latency" value={summary?`${fmt(summary.observed_p95_latency_ms)} ms`:'—'} sub="Historical request timings"/><Metric icon={<Database/>} label="Recorded media bytes" value={summary?`${fmt(summary.observed_total_bytes/1024/1024)} MB`:'—'} sub="Sum of content_size"/><Metric icon={<AlertTriangle/>} label="Recorded errors" value={summary?.errors??'—'} sub="is_error flag in CSV"/></section>
 <section className="content-grid"><Panel title="TRACE REPLAY" subtitle="Chronological records from your dataset" icon={<Activity/>} action={<span className={`mini-status ${connected?'green':''}`}>{connected?'REPLAYING':'PAUSED'}</span>}><div className="chart-wrap"><ResponsiveContainer width="100%" height="220"><AreaChart data={chart}><defs><linearGradient id="latfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#35d6a2" stopOpacity={.35}/><stop offset="100%" stopColor="#35d6a2" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="#203145"/><XAxis dataKey="i" stroke="#72859c" tickLine={false}/><YAxis stroke="#72859c" tickLine={false}/><Tooltip contentStyle={{background:'#101d2d',border:'1px solid #26394f',borderRadius:10}}/><Area type="monotone" dataKey="latency" name="Recorded latency (ms)" stroke="#35d6a2" fill="url(#latfill)"/></AreaChart></ResponsiveContainer></div><div className="chart-caption"><span><i className="legend-dot mint"/>Recorded request latency</span><span>{events.length} recent replay events</span></div><div className="trace-table"><div className="table-head"><span>HOSTNAME</span><span>ASSET</span><span>STATUS</span><span>LATENCY</span></div>{events.slice(-5).reverse().map((e,i)=><div className="table-row" key={`${e.index}-${i}`}><span className="host-cell">{e.host}</span><span>{e.asset}</span><span className={e.status===200?'status-ok':'status-warn'}>{e.status}</span><span>{fmt(e.latency)} ms</span></div>)}{!events.length&&<div className="empty">Start trace replay to view actual recorded requests.</div>}</div></Panel>
 <Panel title="MODEL INFERENCE" subtitle="Trained on Bandwidth.csv only" icon={<BrainCircuit/>}><div className="model-card"><div className="model-title"><span className="model-icon blue"><BrainCircuit/></span><div><b>LSTM demand forecast</b><small>Next 10-second bin · model output</small></div><span className="trained">TRAINED</span></div><div className="forecast-values"><div><small>Predicted requests</small><strong>{forecast?fmt(forecast.forecast_requests_next_bin,2):'—'}</strong></div><div><small>Predicted bytes</small><strong>{forecast?`${fmt(forecast.forecast_bytes_next_bin/1024,1)} <i>KB</i>`:'—'}</strong></div></div><div className="model-foot">Forecast is a model estimate, not a guarantee. Validate on a time-ordered holdout.</div></div><div className="model-card"><div className="model-title"><span className="model-icon purple"><Network/></span><div><b>GNN hostname graph</b><small>Observed host co-occurrence graph</small></div><span className="trained">TRAINED</span></div><div className="graph-nodes">{(graph?.nodes||[]).map((n,i)=><div className="graph-node" key={n.hostname}><div className="node-dot">{i+1}</div><div><b>{n.hostname}</b><small>Trace mean latency: {fmt(n.estimated_mean_latency_ms_from_trace)} ms</small></div></div>)}</div><div className="model-foot">Graph links are based on hostnames appearing in the same observed minute; no geography is inferred.</div></div></Panel></section>
 <section className="content-grid lower"><Panel title="LIVE API LATENCY" subtitle="Measured from this browser to the deployed API" icon={<Wifi/>} action={<button className="icon-btn" onClick={measureLatency}><RefreshCw size={15}/></button>}><div className="latency-card"><div><small>Browser round-trip time</small><strong>{latency?`${latency.ms} ms`:'—'}</strong><p>{latency?.kind||'Press measure to send a real HTTP request.'}</p></div><button className="secondary" onClick={measureLatency}>Measure now</button></div><div className="server-metrics">{metrics.slice(-4).reverse().map((m,i)=><div key={i}><span>{m.path}</span><b>{m.server_processing_ms} ms</b></div>)}</div><p className="footnote">Browser RTT includes the network path. X-Server-Processing-Ms measures server-side request handling. Neither is a CDN edge-to-edge benchmark by itself.</p></Panel>
 <Panel title="HLS PLAYER" subtitle="Play a browser-accessible HLS stream" icon={<Video/>}><div className="player"><video ref={videoRef} controls playsInline/></div><div className="url-row"><input value={hlsUrl} onChange={e=>setHlsUrl(e.target.value)} placeholder="https://your-domain/path/stream.m3u8"/><button className="primary compact" onClick={loadVideo}>Load</button></div><p className="player-status">{videoStatus}</p><p className="footnote">The source URLs in Bandwidth.csv use captured internal hostnames and may not resolve publicly. Supply an accessible HLS URL; browser CORS policies apply. Video playback is separate from model training.</p></Panel></section>
 <footer><div className="footer-brand"><Activity size={17}/> EDGECAST</div><span>Built from the supplied Bandwidth.csv · no synthetic training data</span><span>Public cloud deployment required for external access</span></footer></main></div>
}
function Metric({icon,label,value,sub}){return <div className="metric-card"><div className="metric-top"><span className="metric-icon">{icon}</span><span className="metric-label">{label}</span></div><strong>{value}</strong><small>{sub}</small></div>}
function Panel({title,subtitle,icon,action,children}){return <div className="panel"><div className="panel-head"><div className="panel-icon">{icon}</div><div className="panel-heading"><b>{title}</b><small>{subtitle}</small></div>{action}</div>{children}</div>}

createRoot(document.getElementById('root')).render(<App/>);
