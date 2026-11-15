// Original lab topology: real CoAP endpoints, simulated CSMA channel.
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/csma-module.h"
#include "ns3/tap-bridge-module.h"
using namespace ns3;
int main(int argc, char* argv[]) {
  double delayMs=20, loss=0, duration=3600;
  uint32_t seed=1, run=1;
  std::string pcap="ghost";
  CommandLine cmd(__FILE__);
  cmd.AddValue("delayMs", "CSMA one-way propagation delay in ms", delayMs);
  cmd.AddValue("loss", "Receive packet error probability, 0..1", loss);
  cmd.AddValue("duration", "Wall-clock run duration in seconds", duration);
  cmd.AddValue("seed", "RNG seed", seed);
  cmd.AddValue("run", "RNG run number", run);
  cmd.AddValue("pcap", "Capture path prefix", pcap);
  cmd.Parse(argc, argv);
  NS_ABORT_MSG_IF(delayMs<0 || loss<0 || loss>1 || duration<=0, "Invalid arguments");
  RngSeedManager::SetSeed(seed); RngSeedManager::SetRun(run);
  GlobalValue::Bind("SimulatorImplementationType", StringValue("ns3::RealtimeSimulatorImpl"));
  GlobalValue::Bind("ChecksumEnabled", BooleanValue(true));
  NodeContainer nodes; nodes.Create(2);
  CsmaHelper csma;
  csma.SetChannelAttribute("DataRate", StringValue("10Mbps"));
  csma.SetChannelAttribute("Delay", TimeValue(Seconds(delayMs/1000.0)));
  NetDeviceContainer devs=csma.Install(nodes);
  for(uint32_t i=0;i<2;i++) {
    Ptr<RateErrorModel> em=CreateObject<RateErrorModel>();
    em->SetAttribute("ErrorUnit", EnumValue(RateErrorModel::ERROR_UNIT_PACKET));
    em->SetAttribute("ErrorRate", DoubleValue(loss));
    em->AssignStreams(10+i);
    devs.Get(i)->SetAttribute("ReceiveErrorModel", PointerValue(em));
    TapBridgeHelper tap;
    tap.SetAttribute("Mode", StringValue("UseBridge"));
    tap.SetAttribute("DeviceName", StringValue(i==0 ? "gd-tap-c" : "gd-tap-s"));
    tap.Install(nodes.Get(i), devs.Get(i));
  }
  csma.EnablePcapAll(pcap, true);
  Simulator::Stop(Seconds(duration)); Simulator::Run(); Simulator::Destroy();
}
