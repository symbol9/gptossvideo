# agency/agency.py

from agency_swarm import Agency
from .SupportAgent.SupportAgent import SupportAgent

support_agent = SupportAgent()

agency = Agency(
    support_agent,
    communication_flows=[],
)