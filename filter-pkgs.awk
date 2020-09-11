# List the packages from a Pipfile excluding those provided by AWS python3.8
# environment

function is_provided(pkgname) {
    return pkgname == "boto3" || pkgname == "botocore"
}

BEGIN {
    ON=0
    count=0
    FS=" = "
    printf "{"
}

{
    if ($1 == "[packages]") {
        ON=1
    } else if ($1 ~ /^\[/) {
        ON=0
    } else if (ON && NF > 0 && ! is_provided($1)) {
        if (count > 0) {
           printf ", "
        }
        printf "\"%s\": %s", tolower($1), $2
        count += 1
    }
}

END {
    printf "}"
}
