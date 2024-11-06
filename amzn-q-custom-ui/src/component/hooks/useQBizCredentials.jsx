// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { useQuery } from '@tanstack/react-query';
import { fromWebToken } from "@aws-sdk/credential-providers";
import { v4 as uuidv4 } from 'uuid';

const fetchIdToken = async (issuer, email) => {
    if(!issuer) return;
    /**
     * We use a dummy Authorization header to satisfy the TVM's requirement
     * which uses a custom Lambda Authorizer which validates per requesting
     * domains
     */
    const dummyAuth = btoa('dummy-client:dummy-secret');
    const response = await fetch(`${issuer}/token`, {
        method: 'POST',
        headers: { 
          'Authorization': `Basic ${dummyAuth}`,
          'Content-Type': 'application/json' 
        },
        body: JSON.stringify({ email }),
    });
    if (!response.ok) throw new Error('Failed to fetch ID token');
    const data = await response.json();
    return data.id_token;
};

const createCredentials = async (issuer, email, region, roleArn) => {
  const idToken = await fetchIdToken(issuer, email);
      const provider = fromWebToken({
                roleArn,
                webIdentityToken: idToken,
                clientConfig: { region },
                roleSessionName: `session-${uuidv4()}-${Date.now()}`,
                durationSeconds: 900 // 15 min
            });
    const credentials = await provider();
    return credentials;
};

export const useQbizCredentials = (issuer, email, region, roleArn) => {    
    return useQuery({
      queryKey: ['qbizCredentials', issuer, email, region, roleArn],
      queryFn: () => createCredentials(issuer, email, region, roleArn),
      staleTime: 15 * 60 * 1000, // 16 minutes
      refetchInterval: 15 * 60 * 1000, // Refetch every 16 minutes
      refetchIntervalInBackground: true,
      retry: 3,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      onError: (error) => {
        if (error.message.includes('ExpiredTokenException')) {
          queryClient.invalidateQueries(['qbizCredentials']);
        }
      },
    });
  };