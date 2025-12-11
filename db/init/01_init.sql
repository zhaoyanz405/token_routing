-- Initialize dev and test databases for token_routing
CREATE DATABASE token_routing_dev OWNER "container";
CREATE DATABASE token_routing_test OWNER "container";

GRANT ALL PRIVILEGES ON DATABASE token_routing_dev TO "container";
GRANT ALL PRIVILEGES ON DATABASE token_routing_test TO "container";
