import React from 'react';
import { Cpu, Database, Zap, Wifi, Radio, HardDrive, CircuitBoard, Microscope, Cog } from 'lucide-react';

interface SemiconductorStock {
  ticker: string;
  name: string;
  segment: string;
  icon: React.ReactNode;
}

const SEMICONDUCTOR_STOCKS: SemiconductorStock[] = [
  { ticker: 'MU',   name: 'Micron Technology',        segment: 'Memory (DRAM / NAND Flash)',        icon: <HardDrive size={14} /> },
  { ticker: 'NVDA', name: 'NVIDIA',                   segment: 'AI GPUs & Data Center',             icon: <Cpu size={14} /> },
  { ticker: 'AMD',  name: 'Advanced Micro Devices',    segment: 'CPUs, GPUs & Accelerators',         icon: <Cpu size={14} /> },
  { ticker: 'INTC', name: 'Intel',                    segment: 'CPUs & Foundry Services',           icon: <Cpu size={14} /> },
  { ticker: 'AVGO', name: 'Broadcom',                 segment: 'Networking & Broadband ICs',        icon: <Wifi size={14} /> },
  { ticker: 'QCOM', name: 'Qualcomm',                 segment: 'Mobile Chipsets & 5G Modems',       icon: <Radio size={14} /> },
  { ticker: 'TXN',  name: 'Texas Instruments',         segment: 'Analog & Embedded Processors',      icon: <CircuitBoard size={14} /> },
  { ticker: 'ADI',  name: 'Analog Devices',            segment: 'Analog / Mixed-Signal ICs',         icon: <CircuitBoard size={14} /> },
  { ticker: 'MRVL', name: 'Marvell Technology',        segment: 'Data Infrastructure & Storage',     icon: <Database size={14} /> },
  { ticker: 'ON',   name: 'ON Semiconductor',          segment: 'Power Management & Sensors',        icon: <Zap size={14} /> },
  { ticker: 'MCHP', name: 'Microchip Technology',      segment: 'Microcontrollers & FPGAs',          icon: <Cpu size={14} /> },
  { ticker: 'STM',  name: 'STMicroelectronics',        segment: 'Automotive & Power Semiconductors', icon: <Cog size={14} /> },
  { ticker: 'AMAT', name: 'Applied Materials',         segment: 'Semiconductor Equipment',           icon: <Microscope size={14} /> },
  { ticker: 'LRCX', name: 'Lam Research',              segment: 'Wafer Fabrication Equipment',       icon: <Microscope size={14} /> },
  { ticker: 'KLAC', name: 'KLA Corporation',           segment: 'Process Control & Metrology',       icon: <Microscope size={14} /> },
];

function StocksList() {
  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h2 className="text-lg font-bold text-white">Semiconductor Coverage</h2>
        <p className="text-sm text-gray-400 mt-1">
          {SEMICONDUCTOR_STOCKS.length} stocks tracked across memory, logic, analog, and equipment segments.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-2">
        {SEMICONDUCTOR_STOCKS.map((stock) => (
          <div
            key={stock.ticker}
            className="flex items-center gap-4 px-4 py-3 bg-[#0f1219] border border-[#202532] rounded-xl hover:border-blue-500/30 transition-colors"
          >
            <div className="w-14 h-8 bg-[#161b24] rounded-lg flex items-center justify-center text-xs font-mono font-bold text-blue-400 tracking-wider border border-[#202532]">
              {stock.ticker}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-white">{stock.name}</div>
              <div className="text-xs text-gray-500 flex items-center gap-1.5 mt-0.5">
                <span className="text-gray-600">{stock.icon}</span>
                {stock.segment}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default StocksList;
