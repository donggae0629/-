import mojito
import pprint

key = "PSbXVS0dw1m9I8Btzs3mzEjJje9sfBikDcQe"
secret = "bXeF6dX0TEQQ/GUsTZx3qxzlr7FFDMxHTeMGDLJVg8TqersI8zZRCa8gOjDb6VZdEXTMPAbszRBtVYj0R+uqik8L3l2l7neOgy4mE23+IPUF0OK8HMdUK5B4jE1Xr9zyN72rN2PmekJMgz28ON/FyWfTIlNRNITVkcgc013V+yqhy1mJXaw="
acc_no = "50153970-01"

broker = mojito.KoreaInvestment(
    api_key=key,
    api_secret=secret,
    acc_no=acc_no,
    mock=True
)
resp = broker.fetch_balance()
pprint.pprint(resp)
