# List the poetry managed dependencies excluding those provided by AWS python3.8
# environment

function is_provided(pkgname) {
    return pkgname == "boto3" || pkgname == "botocore"
}

$1 ~ /^[a-z]/ && ! is_provided($1) {
    printf "%s==%s\n", $1, $2
}
