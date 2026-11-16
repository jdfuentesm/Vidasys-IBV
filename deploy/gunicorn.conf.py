import os
bind = os.environ.get('BIND_ADDRESS', '0.0.0.0:' + os.environ.get('PORT', '8000'))
workers = int(os.environ.get('WEB_CONCURRENCY', '2'))
threads = 1
timeout = 60
max_requests = 1000
max_requests_jitter = 50
accesslog = '-'
errorlog = '-'
forwarded_allow_ips = os.environ.get('PROXY_ALLOWED_IPS', '127.0.0.1')
