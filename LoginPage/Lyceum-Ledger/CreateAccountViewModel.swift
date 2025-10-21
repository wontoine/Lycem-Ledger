//
//  CreateAccountViewModel.swift
//  Lyceum-Ledger
//
//  Created by Antoine Nguyen on 10/16/25.
//
import SwiftUI

@MainActor
class CreateAccountViewModel: ObservableObject {
    @Published var username = ""
    @Published var email = ""
    @Published var password = ""
    @Published var confirmPassword = ""
    
    @Published var isLoading = false
    @Published var errorMessage: String?
    
    // Client-side validation
    var isSignUpButtonDisabled: Bool {
        // Ensure passwords match and are not empty
        return username.isEmpty || email.isEmpty || password.isEmpty || password != confirmPassword || isLoading
    }
    
    func createAccount() async {
        // 1. Set loading state
        isLoading = true
        errorMessage = nil
        
        // 2. Perform your network call to the sign-up endpoint
        //    (This logic would be similar to your loginUser function)
        print("Creating account for \(username)...")
        
        // 3. Handle success or failure
        // On success, you might dismiss the sheet
        // On failure, set the errorMessage
        
        isLoading = false
    }
}
